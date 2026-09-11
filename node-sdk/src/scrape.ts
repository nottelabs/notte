/**
 * Shared scrape request/response handling for `client.scrape()` and
 * `session.scrape()`, mirroring `PageClient.scrape` in the Python SDK.
 */
import type { DataSpace, ImageData, ScrapeRequest, StructuredDataBaseModel } from '@/lib/client/types.gen';
import { ScrapeFailedError } from '@/errors';

/** Minimal structural view of a Zod schema so `zod` stays an optional import path. */
export interface ZodLikeSchema<T> {
  parse(data: unknown): T;
}

/** Structured extraction result when `raiseOnFailure` is false, like `StructuredData` in Python. */
export interface StructuredData<T> {
  success: boolean;
  error?: string | null;
  data?: T | null;
}

export interface ScrapeOptions<T = unknown> {
  /** A Zod schema or a JSON Schema object describing the data to extract. */
  response_format?: ZodLikeSchema<T> | Record<string, unknown> | null;
  /** JSON Schema to send instead of converting `response_format`. Only used with a Zod schema. */
  json_schema?: Record<string, unknown>;
  /**
   * When true (default) a failed structured extraction throws `ScrapeFailedError`
   * and the extracted data is returned directly. When false the `StructuredData`
   * wrapper is returned so callers can inspect `.success`.
   */
  raiseOnFailure?: boolean;
}

export type SessionScrapeOptions<T = unknown> = Omit<ScrapeRequest, 'response_format'> & ScrapeOptions<T>;

export type ScrapeResult<T> = string | ImageData[] | T | StructuredData<T>;

export function isZodSchema<T>(value: unknown): value is ZodLikeSchema<T> {
  return typeof value === 'object' && value !== null && typeof (value as ZodLikeSchema<T>).parse === 'function';
}

export function requiresSchema(options: { response_format?: unknown; instructions?: string | null }): boolean {
  return Boolean(options.response_format || options.instructions);
}

/**
 * Build the API request body: strips SDK-only options and replaces a Zod
 * `response_format` with its JSON Schema. `instructions` are sent exactly as
 * given; nothing is inferred from the schema.
 */
export async function buildScrapeBody<T>(
  options: SessionScrapeOptions<T>,
): Promise<Omit<ScrapeRequest, 'response_format'> & { response_format?: unknown }> {
  const { raiseOnFailure: _raise, json_schema, response_format, ...rest } = options;
  const body: Omit<ScrapeRequest, 'response_format'> & { response_format?: unknown } = { ...rest };
  if (isZodSchema(response_format)) {
    if (json_schema) {
      body.response_format = json_schema;
    } else {
      const { z } = await import('zod');
      body.response_format = z.toJSONSchema(response_format as never);
    }
  } else if (response_format) {
    body.response_format = response_format;
  }
  return body;
}

/**
 * Post-process a scrape response according to the request options:
 * - `only_images` returns the image list,
 * - `response_format` / `instructions` return the extracted data (validated by
 *   the Zod schema when one was given) or throw `ScrapeFailedError`,
 * - otherwise the markdown string is returned.
 */
export function processScrapeResponse<T = unknown>(
  scrapeResponse: DataSpace | undefined,
  options: SessionScrapeOptions<T> & { instructions?: string | null; only_images?: boolean },
): ScrapeResult<T> {
  if (!scrapeResponse) {
    throw new ScrapeFailedError('empty response');
  }
  const raiseOnFailure = options.raiseOnFailure ?? true;

  if (options.only_images) {
    return scrapeResponse.images ?? [];
  }

  if (requiresSchema(options)) {
    const structured = scrapeResponse.structured as StructuredDataBaseModel | null | undefined;
    if (!structured) {
      throw new ScrapeFailedError('the API returned no structured data. This should not happen, please report it.');
    }
    const success = structured.success ?? false;
    const schema = isZodSchema<T>(options.response_format) ? options.response_format : undefined;

    if (!success) {
      if (raiseOnFailure) {
        throw new ScrapeFailedError(structured.error ?? undefined);
      }
      return { success, error: structured.error ?? null, data: null };
    }

    const data = schema && structured.data != null ? schema.parse(structured.data) : (structured.data as T);
    if (raiseOnFailure) {
      return data;
    }
    return { success, error: structured.error ?? null, data };
  }

  return scrapeResponse.markdown;
}
