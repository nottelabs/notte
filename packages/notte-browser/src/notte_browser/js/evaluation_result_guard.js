// Runs with code, budgets, token, depth, marker and transfer allowances supplied as an array.
// It reproduces what Playwright
// does with a bare expression string (global eval, call the value when it is a
// function, await it), then walks the result with the same routing as
// Playwright's serializer and returns a snapshot built only from values it has
// read and charged. Playwright then serializes the snapshot, never the original,
// so nothing on the page is read after the measurement:
//
// - arrays and objects become copies; each property is read once, getters
//   included, and getters are not run again by Playwright;
// - an Error becomes its message, which is the text the formatter prints;
// - a RegExp carries its source and flags for the active driver's decoder;
// - a Date or URL becomes a tagged object whose toJSON returns the text that
//   was read and charged;
// - a typed array is recognised and sized through the built-in typed-array
//   accessors, not instanceof or .length, and copied into a fresh array.
//
// Built-ins are captured before the user code runs. Every charge is a lower
// bound on what format_evaluation_result writes, so the guard never rejects a
// result the exact budget would accept; non-finite charges are rejected.
async ([code, maxBytes, maxValues, token, maxDepth, resultLimitMarker, allowancePerValue, allowanceFixed]) => {
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
  const substring = attempt(() => String.prototype.substring);
  const keysOf = Object.keys;
  const prototypeOf = Object.getPrototypeOf;
  const createObject = Object.create;
  const setPrototypeOf = Object.setPrototypeOf;
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

  // A top-level `return` (outside any nested function) is illegal in a
  // script, so such code runs as a function body: it compiles as a function
  // body but not as statements in a never-taken block of eval code, where
  // `return` is illegal. Neither check runs the user code.
  const hasTopLevelReturn = (source) => {
    try {
      new Function(source);
    } catch (error) {
      return false;
    }
    try {
      new Function("source", "eval(source)")("if (false) {\n" + source + "\n}");
    } catch (error) {
      return true;
    }
    return false;
  };
  let value = (0, eval)(hasTopLevelReturn(code) ? "(() => {\n" + code + "\n})()" : code);
  if (typeof value === "function") {
    value = value();
  }
  value = await value;

  const fail = (reason) => {
    throw new Error(resultLimitMarker + token + ":" + reason);
  };
  const tooLarge = () => fail("serialized result exceeds " + maxBytes + " bytes");
  // Transfer memory grows with the number of values, not the formatted size:
  // each one becomes several objects in the driver and in Python. Every visit
  // counts once, including repeated references, which Python also expands.
  let values = 0;
  let size = 0;
  // Regex reprs can be truncated by Python, so their source contributes to
  // transfer memory independently of the final text size. Use the same total
  // transfer bound that Python checks before decoding the payload.
  const transferLimit = maxBytes + allowancePerValue * (maxValues + 1);
  let regexTransferSize = 0;
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
  const escapedWidth = (text, limit, ascii = true) => {
    if (text.length + 2 > limit) {
      return limit + 1;
    }
    let width = 2;
    for (let i = 0; i < text.length && width <= limit; i++) {
      const c = text.charCodeAt(i);
      if (c === 0x22 || c === 0x5c) {
        width += 2;
      } else if (c >= 0x20 && (c < 0x7f || !ascii)) {
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
  // The snapshot is built from the guard's own nodes, and the guard writes
  // the JSON itself (see write below), so nothing on the page serializes it.
  // Values JSON cannot express become {[token]: kind, v: text}; the per-call
  // token cannot appear in page data.
  const newArray = () => setPrototypeOf([], null);
  const node = (kind, a, b) => {
    const n = newArray();
    n[0] = kind;
    n[1] = a;
    n[2] = b;
    return n;
  };
  const tag = (kind, payload) => node("t", kind, payload);
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
      // JSON escaping belongs to the transfer budget. Python's final regex
      // text can be much shorter than its source; the formatter checks that
      // output separately after the active driver decodes the pattern.
      regexTransferSize += escapedWidth(source, transferLimit - regexTransferSize, false);
      regexTransferSize += escapedWidth(flags, transferLimit - regexTransferSize, false);
      if (!(regexTransferSize <= transferLimit)) {
        tooLarge();
      }
      return node("r", source, flags);
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
      // Playwright unpacks Float32Array and Float64Array elements as floats;
      // JSON would turn 1.0 into the integer 1, so the array is tagged.
      const array = node("a", list);
      return kind === "Float32Array" || kind === "Float64Array" ? tag("fa", array) : array;
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
      const items = newArray();
      const copy = node("a", items);
      copies.set(item, copy);
      charge(2 + item.length);
      for (let i = 0; i < item.length; ++i) {
        items[i] = visit(item[i], depth + 1);
      }
      return done(copy);
    }
    const keys = newArray();
    const vals = newArray();
    const copy = node("o", keys, vals);
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
      chargeText(name, false);
      charge(1);
      keys[entries] = name;
      if (name === "toJSON" && typeof entry === "function") {
        charge(2);
        vals[entries] = node("e");
      } else {
        vals[entries] = visit(entry, depth + 1);
      }
      entries += 1;
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
  // A top-level string is sent as is: its length, which a page cannot
  // override, was already checked against maxBytes.
  if (typeof value === "string") {
    chargeText(value, true);
    return "s" + value;
  }
  // A cycle fails the action as a JavaScript error (above) instead of
  // crashing the formatter after the transfer, as it did before.
  const snapshot = visit(value, 0);

  // The JSON is written here with operators, string indexing and length only,
  // none of which a page can override. The writer counts values and depth
  // itself, so whatever the walk produced, the payload holds at most maxValues
  // values; its length must match the length computed alongside it, and fit
  // what the walk measured plus a fixed allowance per value.
  const controlEscapes = {"\u0000": "\\u0000", "\u0001": "\\u0001", "\u0002": "\\u0002", "\u0003": "\\u0003", "\u0004": "\\u0004", "\u0005": "\\u0005", "\u0006": "\\u0006", "\u0007": "\\u0007", "\b": "\\b", "\t": "\\t", "\n": "\\n", "\u000b": "\\u000b", "\f": "\\f", "\r": "\\r", "\u000e": "\\u000e", "\u000f": "\\u000f", "\u0010": "\\u0010", "\u0011": "\\u0011", "\u0012": "\\u0012", "\u0013": "\\u0013", "\u0014": "\\u0014", "\u0015": "\\u0015", "\u0016": "\\u0016", "\u0017": "\\u0017", "\u0018": "\\u0018", "\u0019": "\\u0019", "\u001a": "\\u001a", "\u001b": "\\u001b", "\u001c": "\\u001c", "\u001d": "\\u001d", "\u001e": "\\u001e", "\u001f": "\\u001f"};
  let out = "";
  let expected = 0;
  let written = 0;
  const literal = (text) => {
    out += text;
    expected += text.length;
  };
  const countValue = () => {
    written += 1;
    if (!(written <= maxValues)) {
      fail("result has more than " + maxValues + " values");
    }
  };
  // substring belongs to the page, which may have replaced it before this
  // call, so every copied run is compared with the source string through
  // primitive indexing, which a page cannot override.
  const unreadable = () => {
    throw new Error("evaluate_js result could not be serialized");
  };
  const copyRun = (text, from, to) => {
    const piece = typeof substring === "function" ? apply(substring, text, [from, to]) : undefined;
    if (typeof piece !== "string" || piece.length !== to - from) {
      unreadable();
    }
    for (let k = 0; k < piece.length; k++) {
      if (piece[k] !== text[from + k]) {
        unreadable();
      }
    }
    out += piece;
    expected += to - from;
  };
  const writeString = (text) => {
    const n = text.length;
    let plain = true;
    for (let i = 0; i < n; i++) {
      const c = text[i];
      if (c < " " || c === '"' || c === "\\") {
        plain = false;
        break;
      }
    }
    if (plain) {
      out += '"' + text + '"';
      expected += n + 2;
      return;
    }
    literal('"');
    let run = 0;
    for (let i = 0; i < n; i++) {
      const c = text[i];
      const escape = c === '"' ? '\\"' : c === "\\" ? "\\\\" : c < " " ? controlEscapes[c] : undefined;
      if (escape === undefined) {
        continue;
      }
      if (i > run) {
        copyRun(text, run, i);
      }
      literal(escape);
      run = i + 1;
    }
    if (run < n) {
      copyRun(text, run, n);
    }
    literal('"');
  };
  const writeText = (text) => writeString(typeof text === "string" ? text : "");
  const write = (item, depth) => {
    if (depth > maxDepth + 2) {
      fail("nesting depth exceeds " + maxDepth);
    }
    if (typeof item === "string") {
      countValue();
      writeString(item);
      return;
    }
    if (typeof item === "number") {
      countValue();
      literal(item === item && item !== Infinity && item !== -Infinity ? "" + item : "null");
      return;
    }
    if (typeof item === "boolean") {
      countValue();
      literal(item ? "true" : "false");
      return;
    }
    if (item === null || typeof item !== "object") {
      countValue();
      literal("null");
      return;
    }
    const kind = item[0];
    if (kind === "a") {
      countValue();
      const items = item[1];
      const n = items === null || typeof items !== "object" ? 0 : items.length;
      literal("[");
      for (let i = 0; i < n; i++) {
        if (i > 0) {
          literal(",");
        }
        write(items[i], depth + 1);
      }
      literal("]");
    } else if (kind === "o") {
      countValue();
      const keys = item[1];
      const vals = item[2];
      const n = keys === null || typeof keys !== "object" || vals === null || typeof vals !== "object" ? 0 : keys.length;
      literal("{");
      for (let i = 0; i < n; i++) {
        if (i > 0) {
          literal(",");
        }
        writeText(keys[i]);
        literal(":");
        write(vals[i], depth + 1);
      }
      literal("}");
    } else if (kind === "e") {
      literal("{}");
    } else if (kind === "r") {
      countValue();
      literal("{");
      writeString(token);
      literal(':"r","v":[');
      writeText(item[1]);
      literal(",");
      writeText(item[2]);
      literal("]}");
    } else if (kind === "t") {
      const tagKind = item[1];
      const payload = item[2];
      if (tagKind !== "fa") {
        countValue();
      }
      literal("{");
      writeString(token);
      literal(":");
      writeText(tagKind);
      literal(',"v":');
      if (tagKind === "fa") {
        write(payload, depth + 1);
      } else if (typeof payload === "string") {
        writeString(payload);
      } else {
        literal("null");
      }
      literal("}");
    } else {
      countValue();
      literal("null");
    }
  };
  write(snapshot, 0);
  if (!(out.length === expected)) {
    throw new Error("evaluate_js result could not be serialized");
  }
  if (!(expected <= size + regexTransferSize + allowancePerValue * values + allowanceFixed && expected <= transferLimit)) {
    tooLarge();
  }
  return "j" + out;
}
