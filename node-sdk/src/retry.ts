/**
 * Automatic retries for transient API failures, shared by every request the
 * client sends. The Python SDK implements the same policy in
 * `notte_sdk/_retry.py`.
 *
 * What is retried:
 * - 503 and 529: the API declined the request before doing any work, so every
 *   method is retried.
 * - 502 and 504: a gateway lost or timed out on the upstream response, which
 *   may already have been processed. Only idempotent methods (GET, HEAD,
 *   OPTIONS, PUT, DELETE) are retried, so a POST such as starting a session
 *   or an agent is never sent twice.
 * - Connection failures that happen before the request is sent (connection
 *   refused, connect timeout, temporary DNS failure): every method.
 * - Connection resets and socket errors, which can happen after the request
 *   was sent: idempotent methods only.
 *
 * Nothing else is retried: 500, other 5xx codes, and 4xx always surface as is.
 */

/** Retries after the first attempt, unless `NotteClientConfig.maxRetries` says otherwise. */
export const DEFAULT_MAX_RETRIES = 3;
/** Backoff before the first retry. Doubles with every retry, capped at `RETRY_MAX_DELAY_MS`. */
export const RETRY_BASE_DELAY_MS = 1_000;
export const RETRY_MAX_DELAY_MS = 10_000;
/** A longer `Retry-After` is not waited for: the error is returned instead. */
export const RETRY_AFTER_MAX_MS = 20_000;

const IDEMPOTENT_METHODS = new Set(['GET', 'HEAD', 'OPTIONS', 'PUT', 'DELETE']);
/** Statuses that guarantee the API did no work. */
const REFUSED_STATUSES = new Set([503, 529]);
/** Gateway statuses: the upstream may already have processed the request. */
const GATEWAY_STATUSES = new Set([502, 504]);
/** The connection was never established, so the request was not sent. */
const NOT_SENT_ERROR_CODES = new Set([
  'ECONNREFUSED',
  'EAI_AGAIN',
  'ENETUNREACH',
  'EHOSTUNREACH',
  'UND_ERR_CONNECT_TIMEOUT',
]);
/** The connection broke at an unknown point, possibly after the request was sent. */
const BROKEN_CONNECTION_ERROR_CODES = new Set([
  'ECONNRESET',
  'EPIPE',
  'ETIMEDOUT',
  'UND_ERR_SOCKET',
  'UND_ERR_CLOSED',
]);

export function isIdempotentMethod(method: string): boolean {
  return IDEMPOTENT_METHODS.has(method.toUpperCase());
}

/** Whether a response with this status is retried for this method. */
export function isRetryableStatus(status: number, method: string): boolean {
  return REFUSED_STATUSES.has(status) || (GATEWAY_STATUSES.has(status) && isIdempotentMethod(method));
}

/** Whether a fetch rejection is a connection failure that is retried for this method. */
export function isRetryableNetworkError(error: unknown, method: string): boolean {
  const code = networkErrorCode(error);
  if (code === undefined) return false;
  return NOT_SENT_ERROR_CODES.has(code) || (BROKEN_CONNECTION_ERROR_CODES.has(code) && isIdempotentMethod(method));
}

/** Find the system error code undici attaches to `TypeError: fetch failed`. */
function networkErrorCode(error: unknown, depth = 0): string | undefined {
  if (typeof error !== 'object' || error === null || depth > 4) return undefined;
  const { code, cause, errors } = error as { code?: unknown; cause?: unknown; errors?: unknown };
  if (typeof code === 'string') return code;
  if (Array.isArray(errors) && errors.length > 0) return networkErrorCode(errors[0], depth + 1);
  return networkErrorCode(cause, depth + 1);
}

/**
 * Parse a `Retry-After` header (seconds or an HTTP date) into milliseconds.
 * Returns `undefined` when absent or malformed.
 */
export function parseRetryAfter(header: string | null | undefined, now = Date.now()): number | undefined {
  if (!header) return undefined;
  const value = header.trim();
  if (/^\d+(\.\d+)?$/.test(value)) return Number(value) * 1000;
  const date = Date.parse(value);
  return Number.isNaN(date) ? undefined : Math.max(0, date - now);
}

/** Exponential backoff with full jitter for the retry following attempt `attempt` (0-based). */
export function backoffDelayMs(attempt: number, random: () => number = Math.random): number {
  return random() * Math.min(RETRY_MAX_DELAY_MS, RETRY_BASE_DELAY_MS * 2 ** attempt);
}

/**
 * Delay before retrying a response, or `undefined` when its `Retry-After`
 * asks for more than `RETRY_AFTER_MAX_MS`.
 */
export function retryDelayMs(attempt: number, retryAfter: string | null | undefined, random?: () => number): number | undefined {
  const requested = parseRetryAfter(retryAfter);
  if (requested === undefined) return backoffDelayMs(attempt, random);
  return requested <= RETRY_AFTER_MAX_MS ? requested : undefined;
}

export interface RetryingFetchOptions {
  /** Retries after the first attempt for the request with this signal. `0` disables retries. */
  maxRetries: (signal: AbortSignal | null | undefined) => number;
  /** Absolute time (ms since epoch) after which the request is abandoned, if any. */
  deadline?: (signal: AbortSignal | null | undefined) => number | undefined;
  /** Underlying fetch. Defaults to the global `fetch`, read at call time. */
  fetch?: typeof fetch;
  random?: () => number;
  sleep?: (ms: number, signal: AbortSignal | null | undefined) => Promise<void>;
}

/** Wrap `fetch` with the retry policy described at the top of this module. */
export function createRetryingFetch(options: RetryingFetchOptions): typeof fetch {
  const wait = options.sleep ?? abortableSleep;
  return async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const baseFetch = options.fetch ?? globalThis.fetch;
    const request = input instanceof Request ? input : undefined;
    const method = (request?.method ?? init?.method ?? 'GET').toUpperCase();
    const signal = init?.signal ?? request?.signal;
    const maxRetries = Math.max(0, Math.floor(options.maxRetries(signal) || 0));
    // A Request body is a one-shot stream: send a clone while another attempt may follow.
    const send = (last: boolean) =>
      request && request.body !== null && !last ? baseFetch(request.clone(), init) : baseFetch(input, init);

    for (let attempt = 0; ; attempt++) {
      const last = attempt >= maxRetries;
      let response: Response;
      try {
        response = await send(last);
      } catch (error) {
        if (last || !isRetryableNetworkError(error, method)) throw error;
        const delay = backoffDelayMs(attempt, options.random);
        if (!fitsDeadline(delay)) throw error;
        warn(`${method} request failed (${networkErrorCode(error)})`, delay, attempt, maxRetries);
        await wait(delay, signal);
        continue;
      }
      if (last || !isRetryableStatus(response.status, method)) return response;
      const delay = retryDelayMs(attempt, response.headers.get('retry-after'), options.random);
      if (delay === undefined || !fitsDeadline(delay)) return response;
      await response.body?.cancel().catch(() => undefined);
      warn(`${method} request returned ${response.status}`, delay, attempt, maxRetries);
      await wait(delay, signal);
    }

    function fitsDeadline(delay: number): boolean {
      const deadline = options.deadline?.(signal);
      return deadline === undefined || Date.now() + delay < deadline;
    }
  };
}

function warn(reason: string, delay: number, attempt: number, maxRetries: number): void {
  console.warn(`${reason}, retrying in ${(delay / 1000).toFixed(1)}s (${attempt + 1}/${maxRetries})`);
}

function abortableSleep(ms: number, signal: AbortSignal | null | undefined): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(signal.reason);
      return;
    }
    const onAbort = () => {
      clearTimeout(timer);
      reject(signal?.reason);
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}
