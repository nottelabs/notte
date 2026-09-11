/**
 * Typed error hierarchy mirroring `notte_sdk.errors` and the `notte_core` errors
 * the Python SDK raises. Every error thrown by the SDK extends `NotteError`, so
 * callers can `catch (e) { if (e instanceof NotteError) ... }` and branch on the
 * concrete class or on `NotteAPIError.statusCode`.
 */
import type { SerializedError } from '@/lib/client/types.gen';

export class NotteError extends Error {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = new.target.name;
  }
}

/**
 * Body of a failed HTTP response, best effort. JSON bodies are exposed as-is;
 * non-JSON bodies (HTML error pages, empty 502s) are wrapped as `{ message }`.
 */
export type NotteAPIErrorBody = Record<string, unknown>;

function describeBody(error: NotteAPIErrorBody): string {
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

/** The API answered with a non-2xx status. */
export class NotteAPIError extends NotteError {
  readonly path: string;
  readonly statusCode: number;
  readonly error: NotteAPIErrorBody;
  readonly response: Response | undefined;

  constructor(path: string, statusCode: number, error: NotteAPIErrorBody, response?: Response) {
    super(`Request to \`${path}\` failed with status code ${statusCode}: ${describeBody(error)}`);
    this.path = path;
    this.statusCode = statusCode;
    this.error = error;
    this.response = response;
  }

  /** The API's own error message, when it sent one. */
  get apiMessage(): string | undefined {
    const message = this.error.message ?? this.error.detail;
    return typeof message === 'string' ? message : undefined;
  }

  static fromBody(path: string, statusCode: number, body: unknown, response?: Response): NotteAPIError {
    return new NotteAPIError(path, statusCode, normalizeErrorBody(body), response);
  }
}

/** The API flagged the failure as an execution error (`x-error-class: NotteApiExecutionError`). */
export class NotteAPIExecutionError extends NotteAPIError {
  constructor(path: string, statusCode: number, error: NotteAPIErrorBody, response?: Response) {
    super(path, statusCode, error, response);
    this.message = `Error on ${path}: ${describeBody(error)}`;
  }
}

/** Missing or rejected credentials. Not retryable. */
export class AuthenticationError extends NotteError {
  constructor(message: string) {
    super(`Authentication failed. ${message}`);
  }
}

/** The request is malformed. Not retryable. */
export class InvalidRequestError extends NotteError {
  constructor(message: string) {
    super(`Invalid request. ${message}`);
  }
}

/** A request or a wait exceeded its deadline. */
export class NotteTimeoutError extends NotteError {}

/** A cloud function run finished with `status: "failed"`. */
export class FailedToRunCloudFunctionError extends NotteError {
  readonly functionId: string;
  readonly functionRunId: string;
  readonly response: unknown;

  constructor(functionId: string, functionRunId: string, response: unknown) {
    super(
      `Function ${functionId} run ${functionRunId} failed: ${
        typeof response === 'string' ? response : describeBody((response ?? {}) as NotteAPIErrorBody)
      }`,
    );
    this.functionId = functionId;
    this.functionRunId = functionRunId;
    this.response = response;
  }
}

/** Structured scrape extraction failed (`StructuredData.success === false`). */
export class ScrapeFailedError extends NotteError {
  readonly structuredError: string | undefined;

  constructor(error: string | undefined) {
    super(`Scrape failed: ${error ?? 'unknown error'}`);
    this.structuredError = error;
  }
}

/**
 * An action executed through `session.execute()` failed. Rehydrated from the
 * structured `exception_detail` payload the API returns, so `errorType` names
 * the concrete server-side error class and the three messages carry the same
 * text Python exposes on `NotteBaseError`.
 */
export class ActionExecutionError extends NotteError {
  readonly errorType: string;
  readonly devMessage: string;
  readonly userMessage: string;
  readonly agentMessage: string;
  readonly shouldRetryLater: boolean;
  readonly shouldNotifyTeam: boolean;

  constructor(detail: SerializedError) {
    super(detail.dev_message || detail.user_message || detail.error_type);
    this.errorType = detail.error_type;
    this.devMessage = detail.dev_message;
    this.userMessage = detail.user_message;
    this.agentMessage = detail.agent_message;
    this.shouldRetryLater = detail.should_retry_later ?? false;
    this.shouldNotifyTeam = detail.should_notify_team ?? false;
  }

  static fromMessage(message: string, errorType = 'NotteBaseError'): ActionExecutionError {
    return new ActionExecutionError({
      error_type: errorType,
      dev_message: message,
      user_message: message,
      agent_message: message,
    });
  }
}

/** `evaluate_js` reported success but the API build predates the data payload. */
export class EvaluateJsNoDataError extends NotteError {
  constructor() {
    super('evaluate_js returned no data. Upgrade the Notte API to a build that returns the evaluated value.');
  }
}

/** The envelope returned by `session.fetch()` could not be decoded. */
export class FetchResponseDecodeError extends NotteError {
  constructor(reason: string) {
    super(`Failed to decode the response returned by the page fetch: ${reason}`);
  }
}

export function normalizeErrorBody(body: unknown): NotteAPIErrorBody {
  if (body && typeof body === 'object' && !Array.isArray(body)) {
    return body as NotteAPIErrorBody;
  }
  if (body === undefined || body === null || body === '') {
    return {};
  }
  return { message: typeof body === 'string' ? body : String(body) };
}

export interface RetryOptions {
  /** Maximum number of attempts, including the first one. */
  maxTries: number;
  /** Delay between attempts in milliseconds. Defaults to 5000 like the Python decorator. */
  delayMs?: number;
  /** Message of the `Error` raised once every attempt failed. */
  errorMessage?: string;
  /** Only retry when this returns true for the thrown error. Defaults to retrying on any error. */
  shouldRetry?: (error: unknown, attempt: number) => boolean;
  /** Called before sleeping between attempts. Defaults to `console.warn`. */
  onRetry?: (error: unknown, attempt: number, maxTries: number) => void;
}

const DEFAULT_RETRY_MESSAGE = 'An error occurred while executing the function. Try again later...';

/**
 * Wrap an async function so it is retried when it throws, mirroring
 * `notte_sdk.errors.retry`. The final failure is raised as an `Error` whose
 * `cause` is the last underlying error.
 *
 * ```ts
 * const start = retry(() => session.start(), { maxTries: 3, delayMs: 1000 });
 * await start();
 * ```
 */
export function retry<TArgs extends unknown[], TResult>(
  fn: (...args: TArgs) => Promise<TResult>,
  options: RetryOptions,
): (...args: TArgs) => Promise<TResult> {
  const {
    maxTries,
    delayMs = 5000,
    errorMessage = DEFAULT_RETRY_MESSAGE,
    shouldRetry = () => true,
    onRetry = (error, attempt, total) => {
      console.warn(`Failed to execute ${fn.name || 'function'}: ${String(error)} (attempt ${attempt}/${total})`);
    },
  } = options;
  if (!Number.isInteger(maxTries) || maxTries < 1) {
    throw new InvalidRequestError('maxTries must be a positive integer');
  }

  return async (...args: TArgs): Promise<TResult> => {
    let lastError: unknown;
    for (let attempt = 1; attempt <= maxTries; attempt += 1) {
      try {
        return await fn(...args);
      } catch (error) {
        lastError = error;
        if (attempt === maxTries || !shouldRetry(error, attempt)) {
          break;
        }
        onRetry(error, attempt, maxTries);
        await sleep(delayMs);
      }
    }
    throw new Error(errorMessage, { cause: lastError });
  };
}

export function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}
