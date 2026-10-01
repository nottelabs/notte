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
# function, await it), then walks the result exactly as Playwright's
# serializer does: same type checks in the same order, same depth-first key
# order, each property read once. Arrays and plain objects are copied as they
# are read and the copy is returned, so Playwright transfers the values that
# were measured and never calls a getter a second time.
#
# Every charge is a lower bound on what format_evaluation_result writes for
# the same value, so the guard never rejects a result the exact budget would
# accept: strings and keys inside containers cost their ASCII-escaped JSON
# width, a top-level string costs its UTF-8 bytes, numbers cost their text,
# repeated references cost one byte, and indentation is not counted. Nesting
# is limited to the formatter's depth. The exact budget still runs after the
# transfer.
PAGE_RESULT_GUARD = """async ([code, maxBytes, token]) => {
  let value = (0, eval)(code);
  if (typeof value === "function") {
    value = value();
  }
  value = await value;
  const maxDepth = %d;
  const fail = (reason) => {
    throw new Error(%s + token + ":" + reason);
  };
  const tooLarge = () => fail("serialized result exceeds " + maxBytes + " bytes");
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
  const is = (item, ctor, tag) => {
    try {
      return (typeof ctor === "function" && item instanceof ctor) || Object.prototype.toString.call(item) === tag;
    } catch (error) {
      return false;
    }
  };
  const isError = (item) => {
    try {
      return item instanceof Error || (Object.getPrototypeOf(item) || {}).name === "Error";
    } catch (error) {
      return false;
    }
  };
  const typedArrays = [
    Int8Array, Uint8Array, Uint8ClampedArray, Int16Array, Uint16Array, Int32Array,
    Uint32Array, Float32Array, Float64Array, BigInt64Array, BigUint64Array,
  ];
  let size = 0;
  const charge = (amount) => {
    size += amount;
    if (size > maxBytes) {
      tooLarge();
    }
  };
  const chargeText = (text, topLevel) => {
    charge(topLevel ? utf8Width(text, maxBytes - size) : escapedWidth(text, maxBytes - size));
  };
  const copies = new Map();
  const visit = (item, depth) => {
    const topLevel = depth === 0;
    if (item && typeof item === "object") {
      const ref =
        (typeof Window === "function" && item instanceof Window && "ref: <Window>") ||
        (typeof Document === "function" && item instanceof Document && "ref: <Document>") ||
        (typeof Node === "function" && item instanceof Node && "ref: <Node>");
      if (ref) {
        chargeText(ref, topLevel);
        return item;
      }
    }
    if (typeof item === "string") {
      chargeText(item, topLevel);
      return item;
    }
    if (typeof item === "number" || typeof item === "boolean" || typeof item === "bigint") {
      charge(String(item).length);
      return item;
    }
    if (item === null || item === undefined || typeof item !== "object") {
      charge(4);
      return item;
    }
    if (isError(item)) {
      // Converted to its message text. Read the data property only, so a
      // message getter still runs once, in Playwright's serializer.
      const message = Object.getOwnPropertyDescriptor(item, "message");
      if (message !== undefined && typeof message.value === "string") {
        chargeText(message.value, topLevel);
      }
      return item;
    }
    if (is(item, Date, "[object Date]") || is(item, URL, "[object URL]")) {
      return item;
    }
    if (is(item, RegExp, "[object RegExp]")) {
      return item;
    }
    for (const ctor of typedArrays) {
      if (is(item, ctor, "[object " + ctor.name + "]")) {
        charge(item.length === 0 ? 2 : 2 + 2 * item.length);
        return item;
      }
    }
    if (copies.has(item)) {
      charge(1);
      return copies.get(item);
    }
    if (depth >= maxDepth) {
      fail("nesting depth exceeds " + maxDepth);
    }
    if (Array.isArray(item)) {
      const copy = [];
      copies.set(item, copy);
      charge(2 + item.length);
      for (let i = 0; i < item.length; ++i) {
        copy.push(visit(item[i], depth + 1));
      }
      return copy;
    }
    // Null prototype so that an own "__proto__" key stays a key.
    const copy = Object.create(null);
    copies.set(item, copy);
    charge(2);
    let entries = 0;
    for (const name of Object.keys(item)) {
      let entry;
      try {
        entry = item[name];
      } catch (error) {
        continue;
      }
      entries += 1;
      chargeText(name, false);
      charge(1);
      if (name === "toJSON" && typeof entry === "function") {
        charge(2);
        copy[name] = entry;
      } else {
        copy[name] = visit(entry, depth + 1);
      }
    }
    if (entries === 0) {
      let json;
      try {
        if (item.toJSON && typeof item.toJSON === "function") {
          json = { value: item.toJSON() };
        }
      } catch (error) {
      }
      if (json) {
        size -= 2;
        copies.set(item, undefined);
        return visit(json.value, depth);
      }
    }
    return copy;
  };
  return visit(value, 0);
}""" % (_MAX_DEPTH, json.dumps(RESULT_LIMIT_MARKER))


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
