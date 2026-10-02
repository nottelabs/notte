/**
 * Helper function to format error messages
 */
import { spawn } from 'node:child_process';

function formatError(error: unknown): string {
	if (typeof error === 'object' && error !== null) {
		// If the error object has a message property, use it
		if ('message' in error && typeof error.message === 'string') {
			return error.message;
		}
		// Otherwise, try to stringify the object
		try {
			return JSON.stringify(error, null, 2);
		} catch {
			return String(error);
		}
	}
	if (error instanceof Error) {
		return error.message;
	}
	return String(error);
}

function openBrowser(url: string): void {
	const platform = process.platform;
	let command: string;
	let args: string[];

	if (platform === 'darwin') {
		command = 'open';
		args = [url];
	} else if (platform === 'win32') {
		command = 'rundll32';
		args = ['url.dll,FileProtocolHandler', url];
	} else {
		command = 'xdg-open';
		args = [url];
	}

	const child = spawn(command, args, {
		detached: true,
		stdio: 'ignore',
	});
	child.on('error', () => {
		// The viewer is a convenience path; avoid crashing the process if no
		// local browser opener exists in the current environment.
	});
	child.unref();
}

/** JSON Schema keywords whose value is a single subschema (or a boolean). */
const SCHEMA_KEYWORDS = new Set([
  'items', 'additionalItems', 'additionalProperties', 'contains', 'propertyNames',
  'not', 'if', 'then', 'else', 'unevaluatedItems', 'unevaluatedProperties',
]);
/** Keywords whose value is an array of subschemas. */
const SCHEMA_ARRAY_KEYWORDS = new Set(['anyOf', 'oneOf', 'allOf', 'prefixItems']);
/**
 * Keywords that shape the value of one specific type and are read by the API's
 * converter from the branch carrying that type.
 */
const TYPE_SCOPED_KEYWORDS = new Set([
  'items', 'prefixItems', 'additionalItems', 'contains', 'unevaluatedItems',
  'properties', 'patternProperties', 'required', 'additionalProperties', 'propertyNames', 'unevaluatedProperties',
  'format',
]);
/** Keywords whose value is a map from name to subschema. */
const SCHEMA_MAP_KEYWORDS = new Set(['properties', 'patternProperties', '$defs', 'definitions', 'dependentSchemas']);

/**
 * Normalise a JSON Schema produced by `z.toJSONSchema()` into the shape the
 * Notte API accepts. zod >= 4.6 emits nullable fields as a type array
 * (`{ type: ['string', 'null'] }`); the API's structured-output validator
 * only understands the `anyOf` form zod used to emit, so expand type arrays
 * back into `anyOf` branches.
 *
 * Only schema-bearing keywords are traversed. Instance-valued keywords such as
 * `default`, `examples`, `const` and `enum` hold caller data, not schemas, and
 * are passed through untouched even if they happen to contain a `type` key.
 *
 * When a type array is expanded, the split mirrors how the API's converter
 * (`notte_core.utils.pydantic_schema.create_model_from_schema`) reads a
 * property: it resolves the Python type by recursing into each `anyOf` branch,
 * so type-scoped keywords (`items`, `properties`, `required`, `format`, ...)
 * move into the matching typed branch, while field constraints and
 * annotations (`minimum`, `minItems`, `enum`, `description`, `default`, ...)
 * are read from the property itself and therefore stay on the parent. A
 * pre-existing `anyOf` is intersected with the allowed types instead of being
 * overwritten.
 */
function normalizeJsonSchema(schema: unknown): unknown {
  if (schema === null || typeof schema !== 'object' || Array.isArray(schema)) return schema;
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(schema as Record<string, unknown>)) {
    if (SCHEMA_KEYWORDS.has(key) || (key === 'items' && Array.isArray(value))) {
      out[key] = Array.isArray(value) ? value.map(normalizeJsonSchema) : normalizeJsonSchema(value);
    } else if (SCHEMA_ARRAY_KEYWORDS.has(key) && Array.isArray(value)) {
      out[key] = value.map(normalizeJsonSchema);
    } else if (SCHEMA_MAP_KEYWORDS.has(key) && value !== null && typeof value === 'object' && !Array.isArray(value)) {
      out[key] = Object.fromEntries(
        Object.entries(value as Record<string, unknown>).map(([name, sub]) => [name, normalizeJsonSchema(sub)]),
      );
    } else {
      out[key] = value;
    }
  }
  if (Array.isArray(out.type)) {
    const { type, anyOf: existing, ...rest } = out;
    const types = type as string[];
    const parent: Record<string, unknown> = {};
    const scoped: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(rest)) {
      (TYPE_SCOPED_KEYWORDS.has(key) ? scoped : parent)[key] = value;
    }
    const typed = (t: string): Record<string, unknown> => (t === 'null' ? { type: t } : { type: t, ...scoped });
    let branches: Record<string, unknown>[];
    if (Array.isArray(existing)) {
      // Intersect the existing alternatives with the allowed types: typed
      // branches survive only if their type is allowed; untyped branches are
      // expanded once per allowed non-null type.
      branches = [];
      for (const branch of existing as Record<string, unknown>[]) {
        if (typeof branch.type === 'string') {
          if (types.includes(branch.type)) branches.push(branch.type === 'null' ? branch : { ...scoped, ...branch });
        } else {
          for (const t of types) if (t !== 'null') branches.push({ ...typed(t), ...branch });
        }
      }
      if (types.includes('null') && !branches.some((b) => b.type === 'null')) branches.push({ type: 'null' });
    } else {
      branches = types.map(typed);
    }
    return { ...parent, anyOf: branches };
  }
  return out;
}

export { formatError, normalizeJsonSchema, openBrowser };
