/**
 * Canonicalize JSON objects in place before generation. Arrays retain their
 * order, including required, unions, prefixItems, defaults, and examples.
 * Keys use ECMAScript order: array indices first, then UTF-16 lexical order.
 * Keep this policy aligned with the SDK's scripts/openapi_order.py.
 * @param {unknown} value
 */
function orderOpenApi(value) {
  if (Array.isArray(value)) {
    value.forEach(orderOpenApi);
  } else if (value !== null && typeof value === 'object') {
    const record = /** @type {Record<string, unknown>} */ (value);
    for (const key of Object.keys(record).sort()) {
      const child = record[key];
      orderOpenApi(child);
      delete record[key];
      // defineProperty also preserves a JSON key named __proto__ as data.
      Object.defineProperty(record, key, {
        value: child, enumerable: true, configurable: true, writable: true,
      });
    }
  }
}

module.exports = { orderOpenApi };
