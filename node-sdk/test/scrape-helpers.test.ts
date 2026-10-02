/**
 * Counterpart of tests/sdk/test_scrape_overload_typing.py for the shared
 * scrape helpers: body construction, raiseOnFailure semantics and the
 * markdown / images / structured branches.
 */
import { describe, expect, expectTypeOf, it } from 'vitest';
import { z } from 'zod';
import { ScrapeFailedError } from '@/errors';
import { normalizeJsonSchema } from '@/utils';
import { buildScrapeBody, processScrapeResponse, type ScrapeResult, type SessionScrapeOptions, type StructuredData } from '@/scrape';
import type { GlobalScrapeOptions } from '@/client';
import type { DataSpace } from '@/lib/client/types.gen';

/** Generated `DataSpace` uses opaque model types; fixtures are plain objects. */
const space = (value: object): DataSpace => value as unknown as DataSpace;

const Product = z.object({ name: z.string(), price: z.number() });
type ProductT = z.infer<typeof Product>;

describe('buildScrapeBody', () => {
  it('sends markdown options through and never invents instructions', async () => {
    const body = await buildScrapeBody({ only_main_content: true, scrape_links: false });
    expect(body).toEqual({ only_main_content: true, scrape_links: false });
    expect(body).not.toHaveProperty('instructions');
  });

  it('converts a Zod schema to JSON Schema and keeps caller instructions verbatim', async () => {
    const body = await buildScrapeBody({ response_format: Product, instructions: 'Extract the product' });
    expect(body.instructions).toBe('Extract the product');
    expect(body.response_format).toMatchObject({ type: 'object', properties: { name: { type: 'string' } } });
  });

  it('prefers a caller-provided json_schema and drops SDK-only options', async () => {
    const schema = { type: 'object', properties: { name: { type: 'string' } } };
    const body = await buildScrapeBody({ response_format: Product, json_schema: schema, raiseOnFailure: false });
    expect(body.response_format).toBe(schema);
    expect(body).not.toHaveProperty('json_schema');
    expect(body).not.toHaveProperty('raiseOnFailure');
  });

  it('passes a raw JSON schema through untouched', async () => {
    const schema = { type: 'object' };
    const body = await buildScrapeBody({ response_format: schema });
    expect(body.response_format).toBe(schema);
  });

  it('forwards the extraction model and omits it when unset', async () => {
    const body = await buildScrapeBody({ instructions: 'Extract the title', model: 'vertex_ai/gemini-3.1-flash-lite' });
    expect(body.model).toBe('vertex_ai/gemini-3.1-flash-lite');
    expect(await buildScrapeBody({ instructions: 'Extract the title' })).not.toHaveProperty('model');
  });

  it('accepts a model on session and client scrape options', () => {
    expectTypeOf<SessionScrapeOptions['model']>().toEqualTypeOf<string | null | undefined>();
    expectTypeOf<GlobalScrapeOptions['model']>().toEqualTypeOf<string | null | undefined>();
  });
});

describe('processScrapeResponse', () => {
  const images = [{ url: 'https://x/y.png', description: 'y', category: 'content' }];
  const dataSpace = space({
    markdown: '# Hello',
    images,
    structured: { success: true, error: null, data: { name: 'Widget', price: 10 } },
  });
  const failedSpace = space({ ...dataSpace, structured: { success: false, error: 'nothing found', data: null } });

  it('returns markdown by default', () => {
    expect(processScrapeResponse(dataSpace, {})).toBe('# Hello');
  });

  it('returns the image list with only_images', () => {
    expect(processScrapeResponse(dataSpace, { only_images: true })).toEqual(images);
    expect(processScrapeResponse(space({ markdown: '', images: null }), { only_images: true })).toEqual([]);
  });

  it('returns the validated model with a Zod response_format', () => {
    const result = processScrapeResponse<ProductT>(dataSpace, { response_format: Product });
    expect(result).toEqual({ name: 'Widget', price: 10 });
  });

  it('returns the raw extracted data with instructions only', () => {
    expect(processScrapeResponse(dataSpace, { instructions: 'extract' })).toEqual({ name: 'Widget', price: 10 });
  });

  it('throws ScrapeFailedError on a failed extraction by default', () => {
    expect(() => processScrapeResponse(failedSpace, { response_format: Product })).toThrow(ScrapeFailedError);
    expect(() => processScrapeResponse(failedSpace, { response_format: Product })).toThrow('nothing found');
  });

  it('returns the StructuredData wrapper with raiseOnFailure false', () => {
    const wrapped = processScrapeResponse<ProductT>(failedSpace, { response_format: Product, raiseOnFailure: false }) as StructuredData<ProductT>;
    expect(wrapped).toEqual({ success: false, error: 'nothing found', data: null });

    const ok = processScrapeResponse<ProductT>(dataSpace, { response_format: Product, raiseOnFailure: false }) as StructuredData<ProductT>;
    expect(ok).toEqual({ success: true, error: null, data: { name: 'Widget', price: 10 } });
  });

  it('throws when the API returns no structured block for a schema request', () => {
    expect(() => processScrapeResponse(space({ markdown: '', structured: null }), { instructions: 'x' })).toThrow(ScrapeFailedError);
  });

  it('throws on an empty response', () => {
    expect(() => processScrapeResponse(undefined, {})).toThrow(ScrapeFailedError);
  });

  it('is typed as ScrapeResult<T>', () => {
    expectTypeOf(processScrapeResponse<ProductT>(dataSpace, { response_format: Product })).toEqualTypeOf<ScrapeResult<ProductT>>();
  });
});

describe('normalizeJsonSchema', () => {
  it('expands zod >= 4.6 nullable type arrays into the anyOf form the API accepts', async () => {
    const Plan = z.object({ name: z.string(), price: z.string().nullable().optional(), tags: z.array(z.string().nullable()) });
    const body = await buildScrapeBody({ response_format: Plan });
    const schema = body.response_format as any;
    expect(schema.properties.price).toEqual({ anyOf: [{ type: 'string' }, { type: 'null' }] });
    expect(schema.properties.tags.items).toEqual({ anyOf: [{ type: 'string' }, { type: 'null' }] });
    expect(JSON.stringify(schema)).not.toContain('"type":["');
  });

  it('leaves schemas without type arrays unchanged', () => {
    const plain = z.toJSONSchema(Product);
    expect(normalizeJsonSchema(plain)).toEqual(plain);
    expect(normalizeJsonSchema(null)).toBeNull();
    expect(normalizeJsonSchema('x')).toBe('x');
  });

  it('does not rewrite instance data inside default, examples, const or enum', () => {
    // An example object that happens to carry a `type` key holding an array must
    // reach the API verbatim; only schema nodes are normalised.
    const Shop = z
      .object({ type: z.array(z.string()), label: z.string().nullable() })
      .meta({ examples: [{ type: ['retail'], label: null }] });
    const schema = normalizeJsonSchema(z.toJSONSchema(Shop)) as any;
    expect(schema.examples).toEqual([{ type: ['retail'], label: null }]);
    expect(schema.properties.label).toEqual({ anyOf: [{ type: 'string' }, { type: 'null' }] });

    const raw = {
      type: 'object',
      properties: { kind: { type: ['string', 'null'], default: { type: ['a', 'b'] }, enum: [{ type: ['x'] }, null] } },
      const: { type: ['keep', 'me'] },
    };
    const out = normalizeJsonSchema(raw) as any;
    expect(out.const).toEqual({ type: ['keep', 'me'] });
    // `default` and `enum` are field-level: they stay on the property, untouched.
    expect(out.properties.kind).toEqual({
      default: { type: ['a', 'b'] },
      enum: [{ type: ['x'] }, null],
      anyOf: [{ type: 'string' }, { type: 'null' }],
    });
  });

  it('splits an expanded type array the way the API converter reads it', () => {
    // Type-scoped keywords move into the typed branch (the converter resolves the
    // Python type by recursing into each anyOf branch); field constraints and
    // annotations stay on the property (the converter reads them from there).
    const raw = {
      type: 'object',
      properties: {
        tags: { type: ['array', 'null'], items: { type: 'string' }, minItems: 1, description: 'labels' },
        meta: { type: ['object', 'null'], properties: { k: { type: 'string' } }, required: ['k'] },
        code: { type: ['string', 'null'], minLength: 2, default: null, format: 'date-time' },
        score: { type: ['number', 'null'], minimum: 1, maximum: 5 },
        either: { type: ['string', 'number', 'null'] },
      },
    };
    const out = normalizeJsonSchema(raw) as any;
    expect(out.properties.tags).toEqual({
      description: 'labels',
      minItems: 1,
      anyOf: [{ type: 'array', items: { type: 'string' } }, { type: 'null' }],
    });
    expect(out.properties.meta).toEqual({
      anyOf: [{ type: 'object', properties: { k: { type: 'string' } }, required: ['k'] }, { type: 'null' }],
    });
    expect(out.properties.code).toEqual({
      minLength: 2,
      default: null,
      anyOf: [{ type: 'string', format: 'date-time' }, { type: 'null' }],
    });
    expect(out.properties.score).toEqual({ minimum: 1, maximum: 5, anyOf: [{ type: 'number' }, { type: 'null' }] });
    expect(out.properties.either.anyOf).toEqual([{ type: 'string' }, { type: 'number' }, { type: 'null' }]);
  });

  it('keeps value-level constraints applying to null and intersects an existing anyOf', () => {
    // `enum` on the property still governs the whole value, so null stays rejected.
    expect(normalizeJsonSchema({ type: ['string', 'null'], enum: ['approved'] })).toEqual({
      enum: ['approved'],
      anyOf: [{ type: 'string' }, { type: 'null' }],
    });
    // An existing anyOf is intersected with the allowed types, not overwritten.
    // The untyped branch is expanded over every allowed type, so null is only
    // accepted through the branch that already accepted it.
    expect(normalizeJsonSchema({ type: ['string', 'null'], anyOf: [{ const: 'approved' }, { type: 'null' }] })).toEqual({
      anyOf: [{ type: 'string', const: 'approved' }, { type: 'null', const: 'approved' }, { type: 'null' }],
    });
    // No existing branch accepts null: the result must not grow a bare null branch.
    expect(normalizeJsonSchema({ type: ['string', 'null'], anyOf: [{ enum: ['approved'] }] })).toEqual({
      anyOf: [{ type: 'string', enum: ['approved'] }, { type: 'null', enum: ['approved'] }],
    });
    // Typed branches outside the allowed types are dropped; no branch accepted
    // null, so none is added.
    expect(
      normalizeJsonSchema({ type: ['string', 'null'], anyOf: [{ type: 'string', minLength: 1 }, { type: 'number' }] }),
    ).toEqual({ anyOf: [{ type: 'string', minLength: 1 }] });
  });

  it('normalises nested schemas under $defs, prefixItems and allOf', () => {
    const raw = {
      $defs: { N: { type: ['number', 'null'] } },
      prefixItems: [{ type: ['string', 'null'] }],
      allOf: [{ properties: { a: { type: ['boolean', 'null'] } } }],
      items: [{ type: ['integer', 'null'] }],
    };
    const out = normalizeJsonSchema(raw) as any;
    expect(out.$defs.N).toEqual({ anyOf: [{ type: 'number' }, { type: 'null' }] });
    expect(out.prefixItems[0]).toEqual({ anyOf: [{ type: 'string' }, { type: 'null' }] });
    expect(out.allOf[0].properties.a).toEqual({ anyOf: [{ type: 'boolean' }, { type: 'null' }] });
    expect(out.items[0]).toEqual({ anyOf: [{ type: 'integer' }, { type: 'null' }] });
  });
});
