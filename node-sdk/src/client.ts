import { createClient } from '@/lib/client/client';
import { Session, type SessionOptions } from '@/session';
import type {
  AgentResponse,
  FunctionListItemResponse,
  GlobalScrapeRequest,
  ListAgentsData,
  ListFunctionsData,
  ListSessionsData,
  ListVaultsData,
  PersonaResponse,
  SessionResponse,
  Vault,
} from '@/lib/client/types.gen';
import { Agent, type AgentConstructor } from '@/agent';
import { NotteVault, type VaultConstructor } from '@/vaults';
import { NottePersona, type PersonaConstructor, type PersonaListOptions } from '@/personas';
import { NotteFunction, type FunctionConstructor } from '@/functions';
import {
  healthCheck,
  listAgents,
  listFunctions,
  listPersonas,
  listSessions,
  listVaults,
  scrapeWebpage,
} from '@/lib/client/sdk.gen';
import {
  buildScrapeBody,
  processScrapeResponse,
  type ScrapeOptions,
  type ScrapeResult,
  type StructuredData,
  type ZodLikeSchema,
} from '@/scrape';
import { SDK_VERSION } from '@/version';
import { RemoteFileStorage, SessionFiles } from '@/files';
import { NotteSearch, type SearchOptions, type SearchResponse, type SearchResultsResponse, type SearchSourcedAnswerResponse, type SearchStructuredResponse } from '@/search';
import { NotteAnything } from '@/anything';
import { NotteSecrets } from '@/secrets';
import { NotteUsage } from '@/usage';
import {
  AuthenticationError,
  InvalidRequestError,
  NotteAPIError,
  NotteAPIExecutionError,
  NotteTimeoutError,
  normalizeErrorBody,
} from '@/errors';
import { createUpgradeErrorMessage, startVersionCheck, upgradeSuggestion } from '@/version-check';

export const DEFAULT_NOTTE_API_URL = 'https://api.notte.cc';
export const DEFAULT_REQUEST_TIMEOUT_MS = 60_000;
/** Request origin header, the Node counterpart of `sdk-python`. */
export const REQUEST_ORIGIN = 'sdk-node';
/**
 * Per-call header read by the client's request interceptor to override the
 * default request timeout. `0` disables the timeout (streaming responses).
 * The header is stripped before the request leaves the process.
 */
export const TIMEOUT_HEADER = 'x-notte-timeout-ms';
const DB_PREVIEW_ENV = 'NOTTE_DB_PREVIEW_BRANCH';
const DB_PREVIEW_HEADER = 'x-db-preview';
const EXECUTION_ERROR_CLASS = 'NotteApiExecutionError';

export interface NotteClientConfig {
  /** API base URL. Defaults to `NOTTE_API_URL` or `https://api.notte.cc`. */
  baseUrl?: string;
  /** API key. Defaults to `NOTTE_API_KEY`. Optional only for relative proxy base URLs. */
  apiKey?: string;
  /** Default per-request timeout in milliseconds. Defaults to 60 000, like the Python SDK. */
  timeoutMs?: number;
  /** Database preview branch. Defaults to `NOTTE_DB_PREVIEW_BRANCH`. Internal. */
  dbPreview?: string;
  /** Log every request like `NotteClient(verbose=True)` in Python. */
  verbose?: boolean;
}

export type SessionListOptions = NonNullable<ListSessionsData['query']>;
export type AgentListOptions = NonNullable<ListAgentsData['query']>;
export type VaultListOptions = NonNullable<ListVaultsData['query']>;
export type FunctionListOptions = NonNullable<ListFunctionsData['query']>;
/** Options of `client.scrape()`: the global scrape request minus `url`, plus the SDK-only scrape options. */
export type GlobalScrapeOptions<T = unknown> = Omit<GlobalScrapeRequest, 'url' | 'response_format'> & ScrapeOptions<T>;

type ResolvedConfig = Required<Pick<NotteClientConfig, 'baseUrl' | 'timeoutMs' | 'verbose'>> &
  Pick<NotteClientConfig, 'apiKey' | 'dbPreview'>;

function isRelativeProxyUrl(baseUrl: string): boolean {
  // '/api/notte' is a same-origin proxy path; '//host' is protocol-relative and not allowed.
  return /^\/(?!\/)/.test(baseUrl);
}

/** Entry point for sessions, agents, functions, vaults, personas, and session files. */
export class NotteClient {
  private readonly config: ResolvedConfig;
  private readonly client = createClient();

  constructor(config: NotteClientConfig = {}) {
    const apiKey = config.apiKey || process.env.NOTTE_API_KEY;
    const baseUrl = config.baseUrl || process.env.NOTTE_API_URL || DEFAULT_NOTTE_API_URL;
    const dbPreview = config.dbPreview || process.env[DB_PREVIEW_ENV] || undefined;
    const timeoutMs = config.timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;
    if (!(timeoutMs >= 0)) {
      throw new InvalidRequestError('timeoutMs must be a non-negative number');
    }

    // Only skip the apiKey check for relative proxy paths (e.g. '/api/notte').
    // Any HTTPS URL—including staging—still requires a key.
    const isProxyMode = isRelativeProxyUrl(baseUrl);
    if (!isProxyMode) {
      const url = new URL(baseUrl);
      const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
      if (url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback)) {
        throw new InvalidRequestError(
          'API base URL must use HTTPS (HTTP is only allowed on loopback for local development)',
        );
      }
    }
    if (!apiKey && !isProxyMode) {
      throw new AuthenticationError(
        'NOTTE_API_KEY needs to be provided. Pass config.apiKey or set the NOTTE_API_KEY environment variable.',
      );
    }

    this.config = { baseUrl, apiKey, timeoutMs, dbPreview, verbose: config.verbose ?? false };

    if (baseUrl !== DEFAULT_NOTTE_API_URL && !isProxyMode) {
      console.warn(`NOTTE_API_URL is set to: ${baseUrl}`);
    }

    // Use redirect:'manual' so we handle 3xx ourselves.
    // Node's undici drops POST bodies on cross-origin 307 redirects
    // (e.g. when the API gateway redirects to AWS Lambda function URLs).
    // throwOnError makes every generated call reject with the typed error
    // built by the error interceptor below, like `BaseClient.request` in Python.
    this.client.setConfig({
      baseUrl: this.config.baseUrl,
      redirect: 'manual',
      throwOnError: true,
    });

    this.client.interceptors.request.use((request: Request) => {
      const headers = new Headers(request.headers);
      if (this.config.apiKey) headers.set('Authorization', `Bearer ${this.config.apiKey}`);
      headers.set('x-notte-request-origin', REQUEST_ORIGIN);
      headers.set('x-notte-sdk-version', SDK_VERSION);
      if (this.config.dbPreview) headers.set(DB_PREVIEW_HEADER, this.config.dbPreview);

      const override = headers.get(TIMEOUT_HEADER);
      headers.delete(TIMEOUT_HEADER);
      const timeoutMs = override !== null ? Number(override) : this.config.timeoutMs;
      const signal = timeoutMs > 0 ? withTimeout(request.signal, timeoutMs) : request.signal;

      if (this.config.verbose) {
        console.info(`Making \`${request.method}\` request to \`${request.url}\``);
      }
      return new Request(request, { headers, signal });
    });

    // Follow 307/308 redirects manually, replaying the original body.
    // Also normalizes Content-Type from text/plain to application/json
    // (AWS Lambda function URLs return JSON with the wrong Content-Type).
    this.client.interceptors.response.use(async (response: Response, request: Request, opts: any) => {
      if ((response.status === 307 || response.status === 308) && response.headers.get('location')) {
        const location = new URL(response.headers.get('location')!, request.url);
        // Never replay a credentialed request over plaintext (loopback excepted for local development).
        const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
        if (location.protocol !== 'https:' && !(location.protocol === 'http:' && loopback)) {
          throw new InvalidRequestError(`Refusing to follow a redirect to an insecure URL: ${location.origin}`);
        }
        const headers = new Headers(request.headers);
        // Strip every credential header on cross-origin redirects to avoid leaking them
        if (location.origin !== new URL(request.url).origin) {
          headers.delete('Authorization');
          headers.delete('x-notte-api-key');
        }
        const headerRecord: Record<string, string> = {};
        headers.forEach((v: string, k: string) => {
          headerRecord[k] = v;
        });
        const redirected = await fetch(location.toString(), {
          method: request.method,
          headers: headerRecord,
          body: opts.serializedBody ?? undefined,
          signal: request.signal,
        });
        return redirected;
      }

      // Normalize text/plain → application/json (Lambda function URLs)
      const ct = response.headers.get('content-type') ?? '';
      if (opts.parseAs !== 'stream' && ct.split(';')[0]?.trim() === 'text/plain') {
        const body = await response.arrayBuffer();
        const headers = new Headers(response.headers);
        headers.set('content-type', 'application/json');
        return new Response(body, { status: response.status, statusText: response.statusText, headers });
      }

      return response;
    });

    // Turn raw failures into the typed error hierarchy.
    this.client.interceptors.error.use((error: unknown, response: Response | undefined, request: Request | undefined) => {
      return this.toTypedError(error, response, request);
    });

    startVersionCheck();
  }

  /**
   * Map the raw value the generated client rejects with into a `NotteError`.
   * HTTP failures become `NotteAPIError` (or `NotteAPIExecutionError` when the
   * API flags them), timeouts become `NotteTimeoutError`, anything else is
   * returned untouched.
   */
  private toTypedError(error: unknown, response: Response | undefined, request: Request | undefined): unknown {
    if (error instanceof NotteAPIError) {
      return error;
    }
    if (response) {
      const path = requestPath(request, response);
      const body = normalizeErrorBody(error);
      if (response.status === 422) {
        const latest = upgradeSuggestion();
        const message = typeof body.message === 'string' ? body.message : '';
        const looksLikeSchemaMismatch =
          message.includes('extra_forbidden') || message.includes('Extra inputs are not permitted') || message.includes("'type':");
        if (latest && looksLikeSchemaMismatch) {
          return new NotteAPIError(
            path,
            response.status,
            { ...body, message: createUpgradeErrorMessage('API returned 422 validation error', latest, message) },
            response,
          );
        }
      }
      if (response.headers.get('x-error-class') === EXECUTION_ERROR_CLASS) {
        return new NotteAPIExecutionError(path, response.status, body, response);
      }
      return new NotteAPIError(path, response.status, body, response);
    }
    if (isTimeoutAbort(error)) {
      // Only the deadline path aborts with a TimeoutError carrying the effective
      // deadline; a caller cancelling its own AbortSignal keeps its AbortError.
      const target = request ? ` to \`${requestPath(request)}\`` : '';
      return new NotteTimeoutError(`Request${target} ${(error as Error).message}`, { cause: error });
    }
    return error;
  }

  /**
   * Add the database preview branch to a websocket URL served by the Notte API.
   * The websocket handshake reads the branch from the query string, so without
   * it a preview-branch session is looked up in the default database.
   */
  withDbPreview(url: string): string {
    if (!this.config.dbPreview) {
      return url;
    }
    const parsed = new URL(url);
    parsed.searchParams.set('db_preview', this.config.dbPreview);
    return parsed.toString();
  }

  /**
   * Health check the Notte API. Resolves when the API answers 200 and rejects
   * with a `NotteAPIError` (or a network error) otherwise.
   */
  async healthCheck(): Promise<void> {
    await healthCheck({ client: this.client });
  }

  /**
   * Create a new session
   */
  Session(options: SessionOptions = {}): Session {
    return new Session(this, options);
  }

  /** Access files owned by a specific session, including closed sessions. */
  Files(sessionId: string): SessionFiles {
    return new SessionFiles(this.getClient(), sessionId);
  }

  /**
   * File storage to attach to a session, the counterpart of `client.FileStorage()`.
   *
   * ```ts
   * const storage = client.FileStorage();
   * await client.Session({ storage }).use(async session => {
   *   await storage.upload('./invoice.pdf');
   *   const files = await storage.list({ source: 'session_download' });
   * });
   * ```
   */
  FileStorage(sessionId?: string): RemoteFileStorage {
    return new RemoteFileStorage(this, sessionId);
  }

  /**
   * Create a new agent
   */
  Agent(options: AgentConstructor): Agent {
    return new Agent(this, options);
  }

  /**
   * Create or access a vault
   */
  Vault(options?: VaultConstructor): NotteVault {
    return new NotteVault(this, options);
  }

  /**
   * Create or access a persona
   */
  Persona(options?: PersonaConstructor): NottePersona {
    return new NottePersona(this, options);
  }

  /**
   * Create or access a function
   */
  NotteFunction(options: FunctionConstructor): NotteFunction {
    return new NotteFunction(this, options);
  }

  /** Alias of `NotteFunction`, matching `client.Function` in Python. */
  Function(options: FunctionConstructor): NotteFunction {
    return this.NotteFunction(options);
  }

  /** Sessions listing, the counterpart of `client.sessions.list()`. */
  get sessions() {
    return {
      list: async (options: SessionListOptions = {}): Promise<SessionResponse[]> => {
        const response = await listSessions({ client: this.getClient(), query: options });
        return response.data?.items ?? [];
      },
    };
  }

  /** Agents listing, the counterpart of `client.agents.list()`. */
  get agents() {
    return {
      list: async (options: AgentListOptions = {}): Promise<AgentResponse[]> => {
        const response = await listAgents({ client: this.getClient(), query: options });
        return response.data?.items ?? [];
      },
    };
  }

  /** Vaults listing, the counterpart of `client.vaults.list()`. */
  get vaults() {
    return {
      list: async (options: VaultListOptions = {}): Promise<Vault[]> => {
        const response = await listVaults({ client: this.getClient(), query: options });
        return response.data?.items ?? [];
      },
    };
  }

  /** Functions listing, the counterpart of `client.functions.list()`. */
  get functions() {
    return {
      list: async (options: FunctionListOptions = {}): Promise<FunctionListItemResponse[]> => {
        const response = await listFunctions({ client: this.getClient(), query: options });
        return response.data?.items ?? [];
      },
    };
  }

  /**
   * Web search (`POST /search`).
   *
   * ```ts
   * const { results } = await client.search('notte browser agents');
   * const { answer } = await client.search('what is notte?', { outputType: 'sourcedAnswer' });
   * ```
   */
  async search(query: string, options?: SearchOptions & { outputType?: 'searchResults' }): Promise<SearchResultsResponse>;
  async search(query: string, options: SearchOptions & { outputType: 'sourcedAnswer' }): Promise<SearchSourcedAnswerResponse>;
  async search(query: string, options: SearchOptions & { outputType: 'structured' }): Promise<SearchStructuredResponse>;
  async search(query: string, options: SearchOptions): Promise<SearchResponse>;
  async search(query: string, options: SearchOptions = {}): Promise<SearchResponse> {
    return new NotteSearch(this).search(query, options);
  }

  /** Anything API (`POST /anything/start`). */
  get anything(): NotteAnything {
    return new NotteAnything(this);
  }

  /** Workspace secrets (`/secrets`). */
  get secrets(): NotteSecrets {
    return new NotteSecrets(this);
  }

  /** Usage and billing (`/usage`, `/usage/logs`). */
  get usage(): NotteUsage {
    return new NotteUsage(this);
  }

  /**
   * Personas client for listing and managing personas
   */
  get personas() {
    return {
      list: async (options?: PersonaListOptions): Promise<PersonaResponse[]> => {
        const response = await listPersonas({
          client: this.getClient(),
          query: options || {},
        });
        return (response.data as any)?.items || [];
      },
    };
  }

  /**
   * Get the configured client instance
   */
  getClient() {
    return this.client;
  }

  /**
   * Scrape a webpage directly (without session).
   *
   * ```ts
   * const markdown = await client.scrape('https://www.notte.cc', { only_main_content: true });
   * const product = await client.scrape('https://www.notte.cc', { response_format: Product, instructions: 'Extract the product' });
   * ```
   *
   * With `response_format` or `instructions`, the extracted data is returned
   * directly and a failed extraction throws `ScrapeFailedError`. Pass
   * `raiseOnFailure: false` to receive the `StructuredData` wrapper instead.
   */
  async scrape(url: string, options?: GlobalScrapeOptions<unknown> & { response_format?: undefined; instructions?: undefined | null }): Promise<string>;
  async scrape<T>(url: string, options: GlobalScrapeOptions<T> & { response_format: ZodLikeSchema<T>; raiseOnFailure?: true }): Promise<T>;
  async scrape<T>(url: string, options: GlobalScrapeOptions<T> & { response_format: ZodLikeSchema<T>; raiseOnFailure: false }): Promise<StructuredData<T>>;
  async scrape(url: string, options: GlobalScrapeOptions<unknown>): Promise<ScrapeResult<unknown>>;
  async scrape<T = unknown>(url: string, options: GlobalScrapeOptions<T> = {}): Promise<ScrapeResult<T>> {
    const body = await buildScrapeBody(options);
    const response = await scrapeWebpage({
      client: this.getClient(),
      body: { url, ...body } as GlobalScrapeRequest,
    });
    return processScrapeResponse<T>(response.data, options);
  }

  /**
   * Get the client configuration
   */
  getConfig(): NotteClientConfig {
    return { ...this.config };
  }
}

function requestPath(request: Request | undefined, response?: Response): string {
  const url = request?.url ?? response?.url;
  if (!url) {
    return 'unknown';
  }
  try {
    return new URL(url).pathname;
  } catch {
    return url;
  }
}

function isTimeoutAbort(error: unknown): boolean {
  return typeof error === 'object' && error !== null && (error as { name?: string }).name === 'TimeoutError';
}

function timeoutReason(timeoutMs: number): DOMException {
  return new DOMException(`timed out after ${timeoutMs}ms`, 'TimeoutError');
}

/**
 * Combine the caller's signal with a deadline. `AbortSignal.any` (Node 20.3+)
 * lets the runtime drop the composite signal once the request settles, so a
 * long-lived caller signal never accumulates listeners.
 */
function withTimeout(signal: AbortSignal | null | undefined, timeoutMs: number): AbortSignal {
  const signalAny = (AbortSignal as unknown as { any?: (signals: AbortSignal[]) => AbortSignal }).any;
  if (typeof signalAny === 'function') {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(timeoutReason(timeoutMs)), timeoutMs);
    timer.unref?.();
    const composite = signalAny.call(AbortSignal, signal ? [signal, controller.signal] : [controller.signal]);
    composite.addEventListener('abort', () => clearTimeout(timer), { once: true });
    return composite;
  }
  // Fallback for runtimes without AbortSignal.any.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(timeoutReason(timeoutMs)), timeoutMs);
  timer.unref?.();
  controller.signal.addEventListener('abort', () => clearTimeout(timer), { once: true });
  if (signal) {
    if (signal.aborted) {
      controller.abort(signal.reason);
    } else {
      const forward = () => controller.abort(signal.reason);
      signal.addEventListener('abort', forward, { once: true });
      controller.signal.addEventListener('abort', () => signal.removeEventListener('abort', forward), { once: true });
    }
  }
  return controller.signal;
}
