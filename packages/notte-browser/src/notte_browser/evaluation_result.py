"""Bound conversion allocations without changing the evaluate_js text format."""

import asyncio
import datetime
import json
import math
import re
import secrets
from json.encoder import encode_basestring_ascii
from typing import Any, cast
from urllib.parse import urlparse

from notte_core.config import BrowserBackend, config
from notte_core.data import DataSpace
from notte_core.errors import EvaluateJsResultLimitError

from notte_browser.driver import Page
from notte_browser.errors import PlaywrightError
from notte_browser.js import script

_STRING_CHUNK_CHARS = 8192
_MAX_DEPTH = 128
# Bytes of JSON text a value may take beyond what the guard charges for it:
# the tag that carries a special number, BigInt, Date or URL (about 70 bytes
# with the 32-character token), or the digits of a typed-array element.
_TRANSFER_ALLOWANCE_PER_VALUE = 96

# Prefix of the error thrown by the page-side guard. Each call appends a random
# token that the evaluated code cannot read, so a page error that merely
# contains this text is never mistaken for a limit rejection.
RESULT_LIMIT_MARKER = "notte_evaluate_js_result_limit:"

_FUNCTION_DECLARATION = re.compile(r"^(async)?\s*function(\s|\()")

# Page-side implementation: js/evaluation_result_guard.js
PAGE_RESULT_GUARD = script("evaluation_result_guard.js")


def new_guard_token() -> str:
    """Return a token that identifies one guarded evaluation's limit error."""
    return secrets.token_hex(16)


_EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
_SPECIAL_NUMBERS = {"NaN": math.nan, "Infinity": math.inf, "-Infinity": -math.inf, "-0": -0.0}


class InvalidPagePayloadError(ValueError):
    """The guard's payload could not be decoded."""


def decode_page_result(payload: object, token: str, *, max_bytes: int, max_values: int) -> Any:
    """Decode the guard's payload into the values Playwright would have produced.

    The payload is "s" plus a top-level string, or "j" plus JSON in which values
    JSON cannot express are tagged with the per-call token; each tag becomes
    what Playwright's own decoder returns for that value. The guard bounds the
    payload before sending it; the same bound is checked again here before
    parsing.
    """
    if not isinstance(payload, str) or payload[:1] not in ("s", "j"):
        raise InvalidPagePayloadError("evaluate_js returned an unexpected payload")
    body = payload[1:]
    if payload[0] == "s":
        if len(body) > max_bytes:
            raise EvaluateJsResultLimitError(max_bytes, "output size")
        return body
    if len(body) > max_bytes + _TRANSFER_ALLOWANCE_PER_VALUE * (max_values + 1):
        raise EvaluateJsResultLimitError(max_bytes, "output size")
    text = body

    def untag(item: dict[str, Any]) -> Any:
        kind = item.get(token)
        if kind is None or len(item) != 2:
            return item
        value = item.get("v")
        if kind == "n" and isinstance(value, str):
            return _SPECIAL_NUMBERS[value]
        if kind == "bi" and isinstance(value, str):
            return int(value)
        if kind == "d":
            # Playwright decodes an invalid Date (toJSON() is null) as the epoch.
            if value is None:
                return _EPOCH
            return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=datetime.timezone.utc)
        if kind == "u":
            return urlparse(value)
        if kind == "fa" and isinstance(value, list):
            elements = cast(list[float], value)
            return [float(element) for element in elements]
        return item

    try:
        return json.loads(text, object_hook=untag)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        # The guard writes the payload itself, so this only guards against a
        # corrupted transfer.
        raise InvalidPagePayloadError(f"evaluate_js result is not valid JSON ({type(error).__name__})") from None


def page_expression(code: str) -> str:
    """Prepare user code for the page-side guard's eval.

    Playwright trims expression strings and parenthesizes function declarations
    so that eval yields the function value instead of declaring it. The guard
    evals the code itself, so it needs the same treatment.
    """
    code = code.strip()
    if _FUNCTION_DECLARATION.match(code):
        return f"({code})"
    return code


def page_limit_reason(error_message: str, token: str) -> str | None:
    """Return the guard's reason when the error is this evaluation's limit error."""
    prefix = f"{RESULT_LIMIT_MARKER}{token}:"
    index = error_message.find(prefix)
    if index < 0:
        return None
    return error_message[index + len(prefix) :].splitlines()[0].strip()


def format_evaluation_result(value: Any, *, max_bytes: int) -> str:
    """Preserve raw scalar text and indented JSON, with a UTF-8 output budget.

    A byte buffer avoids retaining millions of encoder chunks. Strings are escaped
    in slices: JSONEncoder.iterencode alone can allocate a whole escaped string
    before yielding it. This budget excludes the already decoded browser result.
    """
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")

    def exceeded(reason: str = "output size") -> EvaluateJsResultLimitError:
        return EvaluateJsResultLimitError(max_bytes, reason)

    def scalar_text(item: Any) -> str:
        # Typed-array protocol values can be bytes. Their repr can expand to
        # four characters per byte, so reject an already oversized value first.
        if isinstance(item, (bytes, bytearray)) and len(item) > max_bytes:
            raise exceeded()
        return "null" if item is None else str(item)

    if not isinstance(value, (dict, list)):
        text = scalar_text(value)
        size = 0
        for start in range(0, len(text), _STRING_CHUNK_CHARS):
            size += len(text[start : start + _STRING_CHUNK_CHARS].encode("utf-8", errors="surrogatepass"))
            if size > max_bytes:
                raise exceeded()
        return text

    output = bytearray()
    active: set[int] = set()

    def write(text: str) -> None:
        # Every JSON fragment is ASCII (ensure_ascii=True, as before).
        if len(output) + len(text) > max_bytes:
            raise exceeded()
        output.extend(text.encode("ascii"))

    def string(text: str) -> None:
        write('"')
        for start in range(0, len(text), _STRING_CHUNK_CHARS):
            write(encode_basestring_ascii(text[start : start + _STRING_CHUNK_CHARS])[1:-1])
        write('"')

    def encode(item: Any, depth: int) -> None:
        if isinstance(item, str):
            string(item)
        elif item is None or isinstance(item, (bool, int, float)):
            write(json.dumps(item))
        elif isinstance(item, (dict, list, tuple)):
            container = cast(dict[Any, Any] | list[Any] | tuple[Any, ...], item)
            if depth >= _MAX_DEPTH:
                raise exceeded(f"nesting depth exceeds {_MAX_DEPTH}")
            identity = id(container)
            if identity in active:
                raise ValueError("Circular reference detected")
            active.add(identity)
            try:
                is_dict = isinstance(item, dict)
                opening, closing = ("{", "}") if is_dict else ("[", "]")
                write(opening)
                if item:
                    indent = "  " * (depth + 1)
                    first = True
                    entries = container.items() if isinstance(container, dict) else enumerate(container)
                    for key, child in entries:
                        write(("\n" if first else ",\n") + indent)
                        first = False
                        if is_dict:
                            if isinstance(key, str):
                                string(key)
                            elif key is None or isinstance(key, (bool, int, float)):
                                string(json.dumps(key))
                            else:
                                raise TypeError(f"keys must be str, int, float, bool or None, not {type(key).__name__}")
                            write(": ")
                        encode(child, depth + 1)
                    write("\n" + "  " * depth)
                write(closing)
            finally:
                active.remove(identity)
        else:
            # Match the previous default=str for dates and other protocol values.
            string(scalar_text(item))

    try:
        encode(value, 0)
        return output.decode("ascii")
    finally:
        # Failed actions retain their exception/traceback in the trajectory.
        # Do not retain the partially encoded output through that traceback.
        output.clear()


async def evaluate_page(page: Page, code: str) -> tuple[bool, str | None, DataSpace | None]:
    """Evaluate under the page-side budgets and return the session's result fields."""
    message: str | None = None
    scraped_data: DataSpace | None = None
    # Evaluate JavaScript code on the page and return the result.
    # The guard runs code with a top-level `return` as a function body.
    guard_token = new_guard_token()
    try:
        evaluate_kwargs: dict[str, bool] = {}
        if config.browser_backend == BrowserBackend.PATCHRIGHT:
            evaluate_kwargs["isolated_context"] = False
        # The guard measures the value inside the page and
        # throws past the budget, so an oversized result is
        # never serialized by the browser, decoded by the
        # driver, or rebuilt as Python objects.
        result = await asyncio.wait_for(
            page.evaluate(
                PAGE_RESULT_GUARD,
                [
                    page_expression(code),
                    config.evaluate_js_max_result_bytes,
                    config.evaluate_js_max_result_values,
                    guard_token,
                    _MAX_DEPTH,
                    RESULT_LIMIT_MARKER,
                    _TRANSFER_ALLOWANCE_PER_VALUE,
                    _TRANSFER_ALLOWANCE_PER_VALUE,
                ],
                **evaluate_kwargs,
            ),
            timeout=config.timeout_evaluate_js_ms / 1000.0,
        )
    except asyncio.TimeoutError:
        success = False
        message = f"JavaScript evaluation timed out after {config.timeout_evaluate_js_ms}ms"
    except PlaywrightError as js_err:
        limit_reason = page_limit_reason(str(js_err), guard_token)
        if limit_reason is not None:
            raise EvaluateJsResultLimitError(config.evaluate_js_max_result_bytes, limit_reason) from None
        success = False
        message = f"JavaScript evaluation failed: {js_err}"
    else:
        result_str: str | None = None
        try:
            # The guard returns the result as one JSON string,
            # decoded once here instead of value by value by
            # Playwright, which cost several times the memory.
            result = decode_page_result(
                result,
                guard_token,
                max_bytes=config.evaluate_js_max_result_bytes,
                max_values=config.evaluate_js_max_result_values,
            )
            result_str = format_evaluation_result(result, max_bytes=config.evaluate_js_max_result_bytes)
        except InvalidPagePayloadError as payload_err:
            message = f"JavaScript evaluation failed: {payload_err}"
        finally:
            # The action's frame can itself be retained when a
            # failure is raised later or saved in the trajectory.
            result = None
        success = result_str is not None
        if result_str is not None:
            scraped_data = DataSpace(markdown=result_str)
    return success, message, scraped_data
