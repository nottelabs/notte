/**
 * Counterpart of tests/sdk/test_scrape_overload_typing.py for the shared
 * scrape helpers: body construction, raiseOnFailure semantics and the
 * markdown / images / structured branches.
 */
import { describe, expect, expectTypeOf, it } from 'vitest';
import { z } from 'zod';
import { ScrapeFailedError } from '@/errors';
import { buildScrapeBody, processScrapeResponse, type ScrapeResult, type StructuredData } from '@/scrape';
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
