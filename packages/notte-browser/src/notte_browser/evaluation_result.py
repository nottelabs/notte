"""Bound conversion allocations without changing the evaluate_js text format."""

import json
import re
from json.encoder import encode_basestring_ascii
from typing import Any, cast

from notte_core.errors.actions import EvaluateJsResultLimitError

_STRING_CHUNK_CHARS = 8192
_MAX_DEPTH = 128

# Marker thrown by the page-side guard. The driver surfaces it as the message
# of a PlaywrightError; the reason text follows the marker.
RESULT_LIMIT_MARKER = "notte_evaluate_js_result_limit:"

_FUNCTION_DECLARATION = re.compile(r"^(async)?\s*function(\s|\()")

# Runs in the page with [code, maxBytes]. It reproduces what Playwright does
# with a bare expression string (global eval, call the value when it is a
# function, await it) and then estimates the serialized size of the value
# before anything is handed to the driver. The estimate counts characters,
# not UTF-8 bytes, so it can admit up to three times the budget for non-ASCII
# text; format_evaluation_result applies the exact budget afterwards. Shared
# references are counted once, as Playwright serializes them as references.
PAGE_RESULT_GUARD = """async ([code, maxBytes]) => {
  let value = (0, eval)(code);
  if (typeof value === "function") {
    value = value();
  }
  value = await value;
  const marker = %s;
  const seen = new Set();
  const stack = [value];
  let size = 0;
  while (stack.length > 0) {
    const item = stack.pop();
    if (item === null || item === undefined) {
      size += 4;
    } else if (typeof item === "string") {
      size += item.length + 2;
    } else if (typeof item !== "object") {
      size += typeof item === "function" ? 2 : 8;
    } else if (seen.has(item)) {
      size += 8;
    } else {
      seen.add(item);
      if (ArrayBuffer.isView(item)) {
        size += Math.ceil(item.byteLength * 4 / 3) + 2;
      } else if (item instanceof ArrayBuffer) {
        size += Math.ceil(item.byteLength * 4 / 3) + 2;
      } else if (item instanceof Date || item instanceof RegExp || item instanceof URL || item instanceof Error) {
        size += String(item).length + 2;
      } else if (Array.isArray(item)) {
        size += 2 + item.length;
        for (let i = 0; i < item.length; i++) {
          stack.push(item[i]);
        }
      } else if (item instanceof Map) {
        size += 2;
        for (const [key, entry] of item) {
          stack.push(key, entry);
        }
      } else if (item instanceof Set) {
        size += 2;
        for (const entry of item) {
          stack.push(entry);
        }
      } else {
        size += 2;
        for (const key of Object.keys(item)) {
          size += key.length + 4;
          stack.push(item[key]);
        }
      }
    }
    if (size > maxBytes) {
      throw new Error(marker + "serialized result exceeds " + maxBytes + " bytes");
    }
  }
  return value;
}""" % json.dumps(RESULT_LIMIT_MARKER)


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


def page_limit_reason(error_message: str) -> str | None:
    """Return the guard's reason when the error came from the page-side guard."""
    index = error_message.find(RESULT_LIMIT_MARKER)
    if index < 0:
        return None
    return error_message[index + len(RESULT_LIMIT_MARKER) :].splitlines()[0].strip()


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
