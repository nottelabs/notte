"""Bound conversion allocations without changing the evaluate_js text format."""

import datetime
import json
import math
import re
import secrets
from json.encoder import encode_basestring_ascii
from typing import Any, cast
from urllib.parse import urlparse

from notte_core.errors.actions import EvaluateJsResultLimitError

_STRING_CHUNK_CHARS = 8192
_MAX_DEPTH = 128

# Prefix of the error thrown by the page-side guard. Each call appends a random
# token that the evaluated code cannot read, so a page error that merely
# contains this text is never mistaken for a limit rejection.
RESULT_LIMIT_MARKER = "notte_evaluate_js_result_limit:"

_FUNCTION_DECLARATION = re.compile(r"^(async)?\s*function(\s|\()")

# Runs in the page with [code, maxBytes, maxValues, token]. It reproduces what Playwright
# does with a bare expression string (global eval, call the value when it is a
# function, await it), then walks the result with the same routing as
# Playwright's serializer and returns a snapshot built only from values it has
# read and charged. Playwright then serializes the snapshot, never the original,
# so nothing on the page is read after the measurement:
#
# - arrays and objects become copies; each property is read once, getters
#   included, and getters are not run again by Playwright;
# - an Error becomes its message, which is the text the formatter prints;
# - a RegExp becomes the {r: {p, f}} object Python receives for it;
# - a Date or URL becomes a tagged object whose toJSON returns the text that
#   was read and charged;
# - a typed array is recognised and sized through the built-in typed-array
#   accessors, not instanceof or .length, and copied into a fresh array.
#
# Built-ins are captured before the user code runs. Every charge is a lower
# bound on what format_evaluation_result writes, so the guard never rejects a
# result the exact budget would accept; non-finite charges are rejected.
PAGE_RESULT_GUARD = """async ([code, maxBytes, maxValues, token]) => {
  const maxDepth = %d;
  // Capture built-ins before the user code runs. A lookup that fails, for
  // example because the page replaced URL, disables only that branch; values
  // it would have handled take the plain-object path, whose snapshot carries
  // no tag, so Playwright still reads nothing from the original.
  const attempt = (read) => {
    try {
      return read();
    } catch (error) {
      return undefined;
    }
  };
  const apply = Reflect.apply;
  const keysOf = Object.keys;
  const prototypeOf = Object.getPrototypeOf;
  const createObject = Object.create;
  const setPrototypeOf = Object.setPrototypeOf;
  const stringify = JSON.stringify;
  const isArray = Array.isArray;
  const objectToString = Object.prototype.toString;
  const tagOf = (item) => apply(objectToString, item, []);
  const accessor = (read) => {
    const get = attempt(read);
    return typeof get === "function" ? (item) => apply(get, item, []) : undefined;
  };
  const typedArrayPrototype = attempt(() => prototypeOf(Uint8Array.prototype));
  const typedArrayKind = accessor(() => Object.getOwnPropertyDescriptor(typedArrayPrototype, Symbol.toStringTag).get);
  const typedArrayBytes = accessor(() => Object.getOwnPropertyDescriptor(typedArrayPrototype, "byteLength").get);
  const typedArraySet = attempt(() => typedArrayPrototype.set);
  const dateTime = accessor(() => Date.prototype.getTime);
  const urlHref = accessor(() => Object.getOwnPropertyDescriptor(URL.prototype, "href").get);
  const regexpSource = accessor(() => Object.getOwnPropertyDescriptor(RegExp.prototype, "source").get);
  const typedArrays = createObject(null);
  for (const name of [
    "Int8Array", "Uint8Array", "Uint8ClampedArray", "Int16Array", "Uint16Array", "Int32Array",
    "Uint32Array", "Float32Array", "Float64Array", "BigInt64Array", "BigUint64Array",
  ]) {
    const Kind = attempt(() => globalThis[name]);
    const width = attempt(() => Kind.BYTES_PER_ELEMENT);
    if (typeof Kind === "function" && typeof width === "number" && width > 0) {
      typedArrays[name] = { Kind, width };
    }
  }
  const WindowType = attempt(() => Window);
  const DocumentType = attempt(() => Document);
  const NodeType = attempt(() => Node);
  const ErrorType = Error;
  const ObjectPrototype = Object.prototype;
  const ArrayPrototype = Array.prototype;
  const instanceOf = (item, Type) => {
    try {
      return typeof Type === "function" && item instanceof Type;
    } catch (error) {
      return false;
    }
  };
  const succeeds = (read, item) => {
    if (read === undefined) {
      return false;
    }
    try {
      read(item);
      return true;
    } catch (error) {
      return false;
    }
  };

  let value = (0, eval)(code);
  if (typeof value === "function") {
    value = value();
  }
  value = await value;

  const fail = (reason) => {
    throw new Error(%s + token + ":" + reason);
  };
  const tooLarge = () => fail("serialized result exceeds " + maxBytes + " bytes");
  // Transfer memory grows with the number of values, not the formatted size:
  // each one becomes several objects in the driver and in Python. Every visit
  // counts once, including repeated references, which Python also expands.
  let values = 0;
  let size = 0;
  const charge = (amount) => {
    if (!(amount >= 0 && amount <= maxBytes)) {
      tooLarge();
    }
    size += amount;
    if (size > maxBytes) {
      tooLarge();
    }
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
  const chargeText = (text, topLevel) => {
    if (topLevel) {
      // Each UTF-16 unit is 1 to 3 UTF-8 bytes, so only a string between the
      // two bounds needs an exact count.
      const room = maxBytes - size;
      charge(text.length * 3 <= room ? text.length : utf8Width(text, room));
    } else {
      charge(escapedWidth(text, maxBytes - size));
    }
  };
  const isError = (item) => {
    try {
      return instanceOf(item, ErrorType) || (prototypeOf(item) || {}).name === "Error";
    } catch (error) {
      return false;
    }
  };
  // Values JSON cannot express are sent as {[token]: kind, v: text}; the
  // per-call token cannot appear in page data. Everything in the snapshot has
  // a null prototype, so JSON.stringify finds no inherited toJSON to call.
  const tag = (kind, text) => {
    const snapshot = createObject(null);
    snapshot[token] = kind;
    snapshot.v = text;
    return snapshot;
  };
  const newArray = () => setPrototypeOf([], null);
  const encodeNumber = (n) =>
    n !== n ? tag("n", "NaN")
    : n === Infinity ? tag("n", "Infinity")
    : n === -Infinity ? tag("n", "-Infinity")
    : n === 0 && 1 / n < 0 ? tag("n", "-0")
    : n;

  const copies = new Map();
  const costs = new Map();
  const visit = (item, depth) => {
    values += 1;
    if (values > maxValues) {
      fail("result has more than " + maxValues + " values");
    }
    const topLevel = depth === 0;
    // Plain objects and arrays, which make up most results, skip the
    // special-type checks below: those identify a type by calling a built-in
    // accessor that throws on a mismatch, which is slow per value.
    let plain = false;
    if (item !== null && typeof item === "object") {
      let proto;
      try {
        proto = prototypeOf(item);
      } catch (error) {
        proto = undefined;
      }
      plain = proto === ObjectPrototype || proto === null || proto === ArrayPrototype;
    }
    if (!plain && item && typeof item === "object") {
      const ref =
        (instanceOf(item, WindowType) && "ref: <Window>") ||
        (instanceOf(item, DocumentType) && "ref: <Document>") ||
        (instanceOf(item, NodeType) && "ref: <Node>");
      if (ref) {
        chargeText(ref, topLevel);
        return ref;
      }
    }
    if (typeof item === "string") {
      chargeText(item, topLevel);
      return item;
    }
    if (typeof item === "number") {
      charge(String(item).length);
      return encodeNumber(item);
    }
    if (typeof item === "boolean") {
      charge(String(item).length);
      return item;
    }
    if (typeof item === "bigint") {
      const digits = String(item);
      charge(digits.length);
      return tag("bi", digits);
    }
    if (item === null || item === undefined || typeof item !== "object") {
      // undefined, functions and symbols arrive in Python as None.
      charge(4);
      return null;
    }
    if (!plain) {
    if (isError(item)) {
      const message = item.message;
      const text = typeof message === "string" ? message : String(message);
      chargeText(text, topLevel);
      return text;
    }
    if (succeeds(dateTime, item)) {
      const text = item.toJSON();
      if (text === null) {
        charge(4);
      } else if (typeof text === "string") {
        // A 24-character ISO timestamp prints as at least 25 characters once
        // Python parses it, so its own width is a lower bound.
        chargeText(text, topLevel);
      } else {
        fail("Date.toJSON() did not return a string");
      }
      return tag("d", text);
    }
    if (succeeds(urlHref, item)) {
      const text = item.toJSON();
      if (typeof text !== "string") {
        fail("URL.toJSON() did not return a string");
      }
      charge(text.length);
      return tag("u", text);
    }
    // The source accessor throws for anything that is not a RegExp, so no
    // page getter runs on other objects. Playwright reads source and flags
    // from the value itself; so does this, once each.
    if (succeeds(regexpSource, item) && tagOf(item) === "[object RegExp]") {
      const source = item.source;
      const flags = item.flags;
      if (typeof source !== "string" || typeof flags !== "string") {
        fail("RegExp source or flags is not a string");
      }
      charge(source.length + flags.length);
      const pattern = createObject(null);
      pattern.p = source;
      pattern.f = flags;
      const snapshot = createObject(null);
      snapshot.r = pattern;
      return snapshot;
    }
    // Kinds Playwright does not encode, such as Float16Array, have no entry
    // and take the plain-object path, as they do in Playwright.
    const kind = typedArrayKind === undefined ? undefined : typedArrayKind(item);
    const typed = typeof kind === "string" ? typedArrays[kind] : undefined;
    if (typed !== undefined && typedArrayBytes !== undefined && typeof typedArraySet === "function") {
      const count = typedArrayBytes(item) / typed.width;
      // Python unpacks a typed array into one object per element.
      values += count;
      if (!(values <= maxValues)) {
        fail("result has more than " + maxValues + " values");
      }
      charge(count === 0 ? 2 : 2 + 2 * count);
      const copy = new typed.Kind(count);
      apply(typedArraySet, copy, [item]);
      const list = newArray();
      for (let i = 0; i < count; ++i) {
        const element = copy[i];
        list[i] = typeof element === "bigint" ? tag("bi", String(element)) : encodeNumber(element);
      }
      return list;
    }
    }
    if (copies.has(item)) {
      // JSON writes a repeated reference out in full, so it costs what its
      // first occurrence cost. An entry still being built is a cycle.
      const cost = costs.get(item);
      if (cost === undefined) {
        throw new Error("evaluate_js result contains a circular reference");
      }
      values += cost.count;
      if (!(values <= maxValues)) {
        fail("result has more than " + maxValues + " values");
      }
      charge(cost.bytes);
      return copies.get(item);
    }
    if (depth >= maxDepth) {
      fail("nesting depth exceeds " + maxDepth);
    }
    const startSize = size;
    const startValues = values;
    const done = (snapshot) => {
      copies.set(item, snapshot);
      costs.set(item, { bytes: size - startSize, count: values - startValues });
      return snapshot;
    };
    if (isArray(item)) {
      const copy = newArray();
      copies.set(item, copy);
      charge(2 + item.length);
      for (let i = 0; i < item.length; ++i) {
        copy[i] = visit(item[i], depth + 1);
      }
      return done(copy);
    }
    const copy = createObject(null);
    copies.set(item, copy);
    charge(2);
    let entries = 0;
    for (const name of keysOf(item)) {
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
        copy[name] = createObject(null);
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
        return done(visit(json.value, depth));
      }
    }
    return done(copy);
  };
  // A cycle fails the action as a JavaScript error (above) instead of
  // crashing the formatter after the transfer, as it did before.
  return stringify(visit(value, 0));
}""" % (_MAX_DEPTH, json.dumps(RESULT_LIMIT_MARKER))


def new_guard_token() -> str:
    """Return a token that identifies one guarded evaluation's limit error."""
    return secrets.token_hex(16)


_EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
_SPECIAL_NUMBERS = {"NaN": math.nan, "Infinity": math.inf, "-Infinity": -math.inf, "-0": -0.0}


def decode_page_result(text: str, token: str) -> Any:
    """Decode the guard's JSON into the values Playwright would have produced.

    The guard tags values JSON cannot express with the per-call token; each tag
    becomes what Playwright's own decoder returns for that value.
    """

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
        return item

    return json.loads(text, object_hook=untag)


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
