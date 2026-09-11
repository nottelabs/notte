/**
 * Error class for authentication/authorization failures in the proxy.
 * Throw this from `authenticate()` to return a 401 response.
 *
 * @example
 * ```typescript
 * authenticate: async (request) => {
 *   const session = await getSession(request);
 *   if (!session) throw new NotteProxyAuthError('Not logged in');
 * }
 * ```
 */
export class NotteProxyAuthError extends Error {
  constructor(message = 'Unauthorized') {
    super(message);
    this.name = 'NotteProxyAuthError';
  }
}

/**
 * Configuration for the Notte API proxy.
 *
 * The proxy forwards incoming HTTP requests to the Notte API,
 * injecting authentication headers server-side so the API key
 * is never exposed to the client.
 */
export interface NotteProxyConfig {
  /**
   * The Notte API key to use for all forwarded requests.
   * Falls back to the NOTTE_API_KEY environment variable when omitted.
   * Can be overridden per-request by returning a string from `authenticate`.
   */
  apiKey?: string;

  /**
   * Base URL of the Notte API.
   * @default 'https://api.notte.cc'
   */
  apiUrl?: string;

  /**
   * Optional async function to authenticate/authorize incoming requests.
   *
   * - Throw a `NotteProxyAuthError` to reject the request (returns 401).
   * - Return `void` to allow the request through using the default `apiKey`.
   * - Return a `string` to override the API key for this specific request
   *   (useful for per-user API keys).
   */
  authenticate?: (request: Request) => Promise<void | string>;

  /**
   * Allowed API endpoint patterns for path validation (SSRF prevention).
   *
   * - `undefined` (default): uses the built-in allowlist derived from the OpenAPI spec.
   * - `RegExp[]`: custom list of allowed patterns.
   * - `false`: disables path validation entirely (not recommended for public-facing proxies).
   */
  allowedPatterns?: RegExp[] | false;

  /**
   * Value for the `x-notte-request-origin` header sent to the Notte API.
   * @default 'sdk-proxy'
   */
  requestOrigin?: string;

  /**
   * List of header names to forward from the incoming request to the Notte API.
   * @default ['content-type', 'accept']
   */
  forwardHeaders?: string[];

  /**
   * Optional hook called just before the request is forwarded to the Notte API.
   * Use this to modify outgoing headers, log requests, etc.
   */
  onBeforeRequest?: (ctx: {
    path: string;
    method: string;
    headers: Headers;
    url: string;
    incomingRequest: Request;
  }) => Promise<void> | void;
}
