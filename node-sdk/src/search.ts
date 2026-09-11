import type { NotteClient } from '@/client';
import type { SearchRequest } from '@/lib/client/types.gen';
import { searchWeb } from '@/lib/client/sdk.gen';

/**
 * Options of `client.search()`: the `POST /search` body minus the query
 * itself (`q`). Extra fields such as `maxResults` or `includeDomains` are
 * forwarded to the search provider untouched.
 */
export type SearchOptions = Omit<SearchRequest, 'q'>;

/** One ranked hit of a `searchResults` search. */
export interface SearchResultItem {
  url: string;
  name: string;
  content: string;
  [key: string]: unknown;
}

/** Response of a search with `outputType: 'searchResults'` (the default). */
export interface SearchResultsResponse {
  results: SearchResultItem[];
  [key: string]: unknown;
}

/** One supporting source of a `sourcedAnswer` search. */
export interface SearchSource {
  url: string;
  name?: string;
  snippet?: string;
  [key: string]: unknown;
}

/** Response of a search with `outputType: 'sourcedAnswer'`. */
export interface SearchSourcedAnswerResponse {
  answer: string;
  sources: SearchSource[];
  [key: string]: unknown;
}

/** Response of a search with `outputType: 'structured'`: the caller-provided schema decides the shape. */
export type SearchStructuredResponse = Record<string, unknown>;

/**
 * Union of every shape `POST /search` can answer with. The OpenAPI spec leaves
 * the response untyped; these interfaces follow the documented shapes at
 * https://docs.notte.cc/concepts/search#response-shapes.
 */
export type SearchResponse = SearchResultsResponse | SearchSourcedAnswerResponse | SearchStructuredResponse;

/**
 * Web search, the counterpart of `POST /search`. Returns ranked results by
 * default, a written answer with sources with `outputType: 'sourcedAnswer'`,
 * or structured output with `outputType: 'structured'`.
 *
 * ```ts
 * const { results } = await client.search('notte browser automation');
 * console.log(results[0].url);
 * ```
 */
export class NotteSearch {
  private readonly client: NotteClient;

  constructor(client: NotteClient) {
    this.client = client;
  }

  /**
   * Search the public web.
   *
   * ```ts
   * const { results } = await notteSearch.search('notte browser automation', { depth: 'fast' });
   * const { answer, sources } = await notteSearch.search('what is notte?', { outputType: 'sourcedAnswer' });
   * ```
   *
   * Rejects with a `NotteAPIError` when the API answers with a non-2xx status.
   */
  async search(query: string, options?: SearchOptions & { outputType?: 'searchResults' | undefined }): Promise<SearchResultsResponse>;
  async search(query: string, options: SearchOptions & { outputType: 'sourcedAnswer' }): Promise<SearchSourcedAnswerResponse>;
  async search(query: string, options: SearchOptions & { outputType: 'structured' }): Promise<SearchStructuredResponse>;
  async search(query: string, options: SearchOptions): Promise<SearchResponse>;
  async search(query: string, options: SearchOptions = {}): Promise<SearchResponse> {
    const response = await searchWeb({
      client: this.client.getClient(),
      body: { ...options, q: query },
      throwOnError: true,
    });
    return response.data as SearchResponse;
  }
}
