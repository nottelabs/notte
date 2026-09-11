import type { SearchRequest } from '@/lib/client/types.gen';

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
