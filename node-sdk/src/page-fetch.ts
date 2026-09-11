/**
 * Issue an HTTP request from the page a session is on, the port of
 * `notte_core.data.fetch`.
 *
 * `session.fetch()` runs the browser's own `fetch()` inside the current page, so
 * the request carries the page's cookies, the session's proxy and the browser's
 * network fingerprint. This module builds the script and reads the result back
 * into a `PageFetchResponse`.
 */
import { FetchResponseDecodeError, InvalidRequestError, NotteError } from '@/errors';

/** A form body (`Record`) or a raw string body. */
export type FetchData = string | Record<string, unknown>;

export interface PageFetchOptions {
  /** HTTP method. Defaults to `GET`. */
  method?: string;
  /** Request headers. */
  headers?: Record<string, string>;
  /** Query parameters appended to the URL (before any fragment). Arrays repeat the key. */
  params?: Record<string, unknown>;
  /** JSON body, sent with `Content-Type: application/json` unless a content type is given. */
  json?: unknown;
  /** Form body (`Record`, sent url-encoded) or a raw string body sent verbatim. */
  data?: FetchData;
  /** Abort the request after this many milliseconds. Must be positive. */
  timeoutMs?: number;
  /**
   * Allow `http:` URLs (and redirects to them). Off by default because the
   * request carries the page's cookies, which would travel in cleartext.
   */
  allowInsecure?: boolean;
}

const CONTENT_TYPE = 'content-type';

function hasHeader(headers: Record<string, string>, name: string): boolean {
  return Object.keys(headers).some(key => key.toLowerCase() === name);
}

/** `urlencode(mapping, doseq=True)`: array values repeat the key. */
function urlencode(mapping: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(mapping)) {
    if (Array.isArray(value)) {
      for (const item of value) search.append(key, String(item));
    } else {
      search.append(key, String(value));
    }
  }
  return search.toString();
}

/** Insert `params` into the query string, before any `#fragment`. */
function withParams(url: string, params: Record<string, unknown>): string {
  const hashIndex = url.indexOf('#');
  const fragment = hashIndex >= 0 ? url.slice(hashIndex) : '';
  const base = hashIndex >= 0 ? url.slice(0, hashIndex) : url;
  const queryIndex = base.indexOf('?');
  const path = queryIndex >= 0 ? base.slice(0, queryIndex) : base;
  const existing = queryIndex >= 0 ? base.slice(queryIndex + 1) : '';
  let query = urlencode(params);
  if (existing) {
    query = `${existing}&${query}`;
  }
  return `${path}?${query}${fragment}`;
}

/**
 * Return the JavaScript that performs the request and serialises the response.
 *
 * The script is an async IIFE, which `evaluateJs` awaits. It returns a JSON
 * string so the value survives the evaluate round-trip unchanged.
 *
 * ```ts
 * const script = buildFetchScript('/api/items', { params: { page: 2 } });
 * const response = responseFromEvaluated(await session.evaluateJs(script));
 * ```
 */
export function buildFetchScript(url: string, options: PageFetchOptions = {}): string {
  const { method = 'GET', headers, params, json, data, timeoutMs, allowInsecure = false } = options;
  if (json !== undefined && data !== undefined) {
    throw new InvalidRequestError('pass either json or data, not both');
  }
  if (timeoutMs !== undefined && !(timeoutMs > 0)) {
    throw new InvalidRequestError('timeout must be positive');
  }

  let requestUrl = url;
  if (params && Object.keys(params).length > 0) {
    // insert before any fragment: the browser strips `#...` before sending,
    // so parameters appended after it would be silently dropped
    requestUrl = withParams(url, params);
  }

  const requestHeaders: Record<string, string> = { ...(headers ?? {}) };
  let body: string | undefined;
  if (json !== undefined) {
    body = JSON.stringify(json);
    if (!hasHeader(requestHeaders, CONTENT_TYPE)) {
      requestHeaders['Content-Type'] = 'application/json';
    }
  } else if (data !== undefined && typeof data !== 'string') {
    body = urlencode(data);
    if (!hasHeader(requestHeaders, CONTENT_TYPE)) {
      requestHeaders['Content-Type'] = 'application/x-www-form-urlencoded';
    }
  } else if (data !== undefined) {
    body = data;
  }

  const init: Record<string, unknown> = {
    method: method.toUpperCase(),
    headers: requestHeaders,
    credentials: 'include',
    redirect: 'follow',
  };
  if (body !== undefined) {
    if (init.method === 'GET' || init.method === 'HEAD') {
      // browser fetch() rejects these outright, so fail before the round-trip
      throw new InvalidRequestError(`${String(init.method)} requests cannot have a body`);
    }
    init.body = body;
  }

  let abort = '';
  if (timeoutMs !== undefined) {
    abort =
      'const controller = new AbortController();' +
      `setTimeout(() => controller.abort(), ${Math.trunc(timeoutMs)});` +
      'init.signal = controller.signal;';
  }
  return (
    '(async () => {' +
    `const init = ${JSON.stringify(init)};` +
    `${abort}` +
    // resolve against the page so relative URLs inherit its scheme, then refuse
    // plaintext: `credentials: 'include'` would send non-Secure cookies in clear
    `const target = new URL(${JSON.stringify(requestUrl)}, location.href);` +
    `const allowInsecure = ${allowInsecure ? 'true' : 'false'};` +
    "if (target.protocol !== 'https:' && !allowInsecure) {" +
    "  throw new Error('Refusing to fetch ' + target.origin + ' over plaintext; pass allowInsecure: true to override');" +
    '}' +
    'const response = await fetch(target.toString(), init);' +
    "if (!allowInsecure && new URL(response.url).protocol !== 'https:') {" +
    "  throw new Error('Refusing to read a response served over plaintext from ' + new URL(response.url).origin + '; pass allowInsecure: true to override');" +
    '}' +
    // ship the raw bytes as base64: `response.text()` would decode with
    // replacement and lose any non-UTF-8 or binary body for good
    'const bytes = new Uint8Array(await response.arrayBuffer());' +
    "let binary = '';" +
    'for (let i = 0; i < bytes.length; i += 0x8000) {' +
    '  binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));' +
    '}' +
    'const headers = {};' +
    'response.headers.forEach((value, key) => { headers[key] = value; });' +
    'return JSON.stringify({status: response.status, url: response.url, headers: headers, body_b64: btoa(binary)});' +
    '})()'
  );
}

const REASON_PHRASES: Record<number, string> = {
  100: 'Continue', 101: 'Switching Protocols', 102: 'Processing', 103: 'Early Hints',
  200: 'OK', 201: 'Created', 202: 'Accepted', 203: 'Non-Authoritative Information', 204: 'No Content',
  205: 'Reset Content', 206: 'Partial Content', 207: 'Multi-Status', 208: 'Already Reported', 226: 'IM Used',
  300: 'Multiple Choices', 301: 'Moved Permanently', 302: 'Found', 303: 'See Other', 304: 'Not Modified',
  305: 'Use Proxy', 307: 'Temporary Redirect', 308: 'Permanent Redirect',
  400: 'Bad Request', 401: 'Unauthorized', 402: 'Payment Required', 403: 'Forbidden', 404: 'Not Found',
  405: 'Method Not Allowed', 406: 'Not Acceptable', 407: 'Proxy Authentication Required', 408: 'Request Timeout',
  409: 'Conflict', 410: 'Gone', 411: 'Length Required', 412: 'Precondition Failed', 413: 'Request Entity Too Large',
  414: 'Request-URI Too Long', 415: 'Unsupported Media Type', 416: 'Requested Range Not Satisfiable',
  417: 'Expectation Failed', 418: "I'm a Teapot", 421: 'Misdirected Request', 422: 'Unprocessable Entity',
  423: 'Locked', 424: 'Failed Dependency', 425: 'Too Early', 426: 'Upgrade Required', 428: 'Precondition Required',
  429: 'Too Many Requests', 431: 'Request Header Fields Too Large', 451: 'Unavailable For Legal Reasons',
  500: 'Internal Server Error', 501: 'Not Implemented', 502: 'Bad Gateway', 503: 'Service Unavailable',
  504: 'Gateway Timeout', 505: 'HTTP Version Not Supported', 506: 'Variant Also Negotiates',
  507: 'Insufficient Storage', 508: 'Loop Detected', 510: 'Not Extended', 511: 'Network Authentication Required',
};

/** `response.raiseForStatus()` rejected a 4xx/5xx response, like `requests.HTTPError`. */
export class PageFetchHTTPError extends NotteError {
  readonly response: PageFetchResponse;

  constructor(response: PageFetchResponse) {
    const kind = response.status < 500 ? 'Client Error' : 'Server Error';
    super(`${response.status} ${kind}: ${response.statusText} for url: ${response.url}`);
    this.response = response;
  }
}

/**
 * The charset the response declares, else `utf-8` when the bytes are valid
 * utf-8. `undefined` means the body is binary or of unknown encoding; `text()`
 * then falls back to a lossy utf-8 decode.
 */
function encodingFor(headers: Record<string, string>, content: Uint8Array): string | undefined {
  const contentType = Object.entries(headers).find(([key]) => key.toLowerCase() === CONTENT_TYPE)?.[1] ?? '';
  for (const param of contentType.split(';').slice(1)) {
    const [name, ...rest] = param.split('=');
    const value = rest.join('=');
    if (name?.trim().toLowerCase() === 'charset' && value) {
      return value.trim().replace(/^["']|["']$/g, '');
    }
  }
  try {
    new TextDecoder('utf-8', { fatal: true }).decode(content);
  } catch {
    return undefined;
  }
  return 'utf-8';
}

/**
 * The response of `session.fetch()`, shaped like the Web `Response` with the
 * final `url` after redirects exposed as a plain property. A non-2xx status is
 * a response, not an error; `raiseForStatus()` throws `PageFetchHTTPError`.
 * `bytes()` holds the exact bytes the server sent, so binary bodies survive;
 * `text()` decodes them with the declared charset, or utf-8 when none is given.
 */
export class PageFetchResponse {
  readonly status: number;
  readonly statusText: string;
  readonly headers: Headers;
  /** The final URL after redirects. */
  readonly url: string;
  /** The declared charset, `utf-8` when the body is valid utf-8, else `undefined`. */
  readonly encoding: string | undefined;
  private readonly content: Uint8Array;

  constructor(init: { status: number; headers: Record<string, string>; url: string; content: Uint8Array }) {
    this.status = init.status;
    this.statusText = REASON_PHRASES[init.status] ?? '';
    this.headers = new Headers(init.headers);
    this.url = init.url;
    this.content = init.content;
    this.encoding = encodingFor(init.headers, init.content);
  }

  get ok(): boolean {
    return this.status >= 200 && this.status < 300;
  }

  /** The raw body bytes. */
  bytes(): Uint8Array {
    return this.content;
  }

  async arrayBuffer(): Promise<ArrayBuffer> {
    return this.content.slice().buffer as ArrayBuffer;
  }

  async text(): Promise<string> {
    let decoder: TextDecoder;
    try {
      decoder = new TextDecoder(this.encoding ?? 'utf-8');
    } catch {
      decoder = new TextDecoder('utf-8');
    }
    return decoder.decode(this.content);
  }

  async json(): Promise<unknown> {
    return JSON.parse(await this.text()) as unknown;
  }

  /** Throw `PageFetchHTTPError` on a 4xx/5xx status, like `requests.Response.raise_for_status()`. */
  raiseForStatus(): this {
    if (this.status >= 400) {
      throw new PageFetchHTTPError(this);
    }
    return this;
  }
}

const BASE64_PATTERN = /^[A-Za-z0-9+/]*={0,2}$/;

function decodeBase64(value: string): Uint8Array {
  if (!BASE64_PATTERN.test(value) || value.length % 4 !== 0) {
    throw new Error('body_b64 is not valid base64');
  }
  return new Uint8Array(Buffer.from(value, 'base64'));
}

/**
 * Turn the envelope `buildFetchScript` returns into a `PageFetchResponse`.
 * Throws `FetchResponseDecodeError` when the envelope cannot be read.
 */
export function responseFromEvaluated(raw: string): PageFetchResponse {
  let payload: unknown;
  try {
    payload = JSON.parse(raw);
  } catch (error) {
    throw new FetchResponseDecodeError(error instanceof Error ? error.message : String(error));
  }
  if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) {
    throw new FetchResponseDecodeError('envelope is not an object');
  }
  const envelope = payload as Record<string, unknown>;
  try {
    if (!('status' in envelope)) {
      throw new Error("'status'");
    }
    const status = Number(envelope.status);
    if (!Number.isInteger(status)) {
      throw new Error(`invalid status: ${String(envelope.status)}`);
    }
    const rawHeaders = envelope.headers ?? {};
    if (typeof rawHeaders !== 'object' || Array.isArray(rawHeaders)) {
      throw new Error('headers is not an object');
    }
    const headers: Record<string, string> = {};
    for (const [key, value] of Object.entries(rawHeaders as Record<string, unknown>)) {
      headers[String(key)] = String(value);
    }
    const content = decodeBase64(String(envelope.body_b64 ?? ''));
    const url = String(envelope.url ?? '');
    return new PageFetchResponse({ status, headers, url, content });
  } catch (error) {
    throw new FetchResponseDecodeError(error instanceof Error ? error.message : String(error));
  }
}
