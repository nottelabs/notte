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
/** Annotation keywords that describe a schema node rather than constrain it. */
const ANNOTATION_KEYWORDS = new Set([
  '$schema', '$id', '$comment', 'title', 'description', 'default', 'examples',
  'deprecated', 'readOnly', 'writeOnly', '$defs', 'definitions',
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
 * When a type array is expanded, annotations (`description`, `default`, ...)
 * stay on the parent and every other keyword (`items`, `properties`, `enum`,
 * `minLength`, an existing `anyOf`, ...) is copied into each non-null branch,
 * so validators that read branches independently keep the full constraint.
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
    const { type, ...rest } = out;
    const types = type as string[];
    const parent: Record<string, unknown> = {};
    const constraints: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(rest)) {
      (ANNOTATION_KEYWORDS.has(key) ? parent : constraints)[key] = value;
    }
    const branches = types.map((t) => (t === 'null' ? { type: t } : { type: t, ...constraints }));
    if (!types.some((t) => t !== 'null')) Object.assign(parent, constraints);
    return { ...parent, anyOf: branches };
  }
  return out;
}

export { formatError, normalizeJsonSchema, openBrowser };
