"""Bound conversion allocations without changing the evaluate_js text format."""

import json
import re
import secrets
from json.encoder import encode_basestring_ascii
from typing import Any, cast

from notte_core.errors.actions import EvaluateJsResultLimitError

_STRING_CHUNK_CHARS = 8192
_MAX_DEPTH = 128

# Prefix of the error thrown by the page-side guard. Each call appends a random
# token that the evaluated code cannot read, so a page error that merely
# contains this text is never mistaken for a limit rejection.
RESULT_LIMIT_MARKER = "notte_evaluate_js_result_limit:"

_FUNCTION_DECLARATION = re.compile(r"^(async)?\s*function(\s|\()")

# Runs in the page with [code, maxBytes, token]. It reproduces what Playwright
# does with a bare expression string (global eval, call the value when it is a
# function, await it) and measures the result before the driver serializes it.
#
# Every charge is a lower bound on what format_evaluation_result writes for the
# same value, so the guard never rejects a result the exact budget would
# accept: strings and keys inside containers cost their ASCII-escaped JSON
# width, a top-level string costs its UTF-8 bytes, numbers cost their text, and
# indentation is not counted. The exact budget still runs after the transfer.
#
# Properties are read through their descriptors and getters are never called,
# so Playwright still reads each getter exactly once. A getter's value is not
# measured here; it is left to the exact budget.
PAGE_RESULT_GUARD = """async ([code, maxBytes, token]) => {
  let value = (0, eval)(code);
  if (typeof value === "function") {
    value = value();
  }
  value = await value;
  const fail = () => {
    throw new Error(%s + token + ":serialized result exceeds " + maxBytes + " bytes");
  };
  const utf8Width = (text, limit) => {
    if (text.length > limit) {
      return limit + 1;
    }
    let width = 0;
    for (let i = 0; i < text.length && width <= limit; i++) {
      const c = text.charCodeAt(i);
      width += c < 0x80 ? 1 : c < 0x800 ? 2 : c >= 0xd800 && c <= 0xdfff ? 2 : 3;
    }
    return width;
  };
  const escapedWidth = (text, limit) => {
    if (text.length + 2 > limit) {
      return limit + 1;
    }
    let width = 2;
    for (let i = 0; i < text.length && width <= limit; i++) {
      const c = text.charCodeAt(i);
      if (c === 0x22 || c === 0x5c) {
        width += 2;
      } else if (c >= 0x20 && c < 0x7f) {
        width += 1;
      } else if (c === 0x08 || c === 0x09 || c === 0x0a || c === 0x0c || c === 0x0d) {
        width += 2;
      } else {
        width += 6;
      }
    }
    return width;
  };
  if (typeof value === "string") {
    if (utf8Width(value, maxBytes) > maxBytes) {
      fail();
    }
    return value;
  }
  const own = (target, key) => {
    const descriptor = Object.getOwnPropertyDescriptor(target, key);
    return descriptor !== undefined && "value" in descriptor ? { value: descriptor.value } : undefined;
  };
  const seen = new Set();
  const stack = [value];
  let size = 0;
  while (stack.length > 0) {
    const item = stack.pop();
    if (typeof item === "string") {
      size += escapedWidth(item, maxBytes - size);
    } else if (typeof item === "number" || typeof item === "boolean" || typeof item === "bigint") {
      size += String(item).length;
    } else if (item === null || typeof item !== "object") {
      size += 4;
    } else if (seen.has(item)) {
      size += 1;
    } else {
      seen.add(item);
      if (ArrayBuffer.isView(item) || item instanceof ArrayBuffer) {
        size += item.byteLength + 3;
      } else if (item instanceof Date) {
        size += 21;
      } else if (item instanceof RegExp || item instanceof URL || item instanceof Error || (typeof Node === "function" && item instanceof Node)) {
        size += 4;
      } else if (Array.isArray(item)) {
        size += 2 + item.length;
        for (let i = item.length - 1; i >= 0; i--) {
          const slot = own(item, i);
          if (slot !== undefined) {
            stack.push(slot.value);
          }
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
          size += escapedWidth(key, maxBytes - size) + 1;
          const slot = own(item, key);
          if (slot !== undefined) {
            stack.push(slot.value);
          }
        }
      }
    }
    if (size > maxBytes) {
      fail();
    }
  }
  return value;
}""" % json.dumps(RESULT_LIMIT_MARKER)


def new_guard_token() -> str:
    """Return a token that identifies one guarded evaluation's limit error."""
    return secrets.token_hex(16)


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
