import { pollAuth, ManagedAuthError, type AuthWaitOptions, type AuthSessionResponse as SessionResponse } from '@/managed-auth';
import { existsSync } from 'node:fs';
import { writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import type { Browser, BrowserContext, Dialog, Page } from 'playwright-core';
import { DEFAULT_REQUEST_TIMEOUT_MS, MAX_RETRIES_HEADER, NotteClient, REQUEST_ORIGIN, TIMEOUT_HEADER } from '@/client';
import { SDK_VERSION } from '@/version';
import type {
  AgentFunctionCodeResponse,
  ApiExecutionResponse,
  ApiSessionStartRequest,
  Cookie,
  ExecutionResponse,
  Observation,
  PageExecuteData,
  ObserveRequest,
  ProfileResponse,
  ReplayResponse,
  ScrapeRequest,
  SessionDebugResponse,
  TabSessionDebugResponse,
} from '@/lib/client/types.gen';
import {
  getSessionScript,
  pageExecute,
  pageObserve,
  pageScrape,
  sessionCookiesGet,
  sessionCookiesSet,
  sessionDebugInfo,
  sessionProfileSave,
  sessionReplay,
  sessionStart,
  sessionAuthReadiness,
  sessionStatus,
  sessionStop,
} from '@/lib/client/sdk.gen';
import { ActionExecutionError, EvaluateJsNoDataError, NotteAPIError, NotteTimeoutError, sleep } from '@/errors';
import type { ExecuteAction } from '@/actions';
import { executeWithCaptcha, type CaptchaExecutionResponse } from '@/captcha';
import { buildFetchScript, responseFromEvaluated, type PageFetchOptions, type PageFetchResponse } from '@/page-fetch';
import { createOrAppendCookiesToFile, readCookiesFile } from '@/cookies';
import {
  buildScrapeBody,
  processScrapeResponse,
  type ScrapeResult,
  type SessionScrapeOptions,
  type StructuredData,
  type ZodLikeSchema,
} from '@/scrape';
import { openBrowser } from '@/utils';
import { backoffDelayMs, isRetryableNetworkError, isRetryableStatus, retryDelayMs } from '@/retry';
import type { RemoteFileStorage } from '@/files';
import { Logger, resolveLogLevel, type LogMethod } from '@/logger';

/** Number of attempts `start()` makes on 5xx errors, like `RemoteSession.start(tries=3)`. */
export const SESSION_START_TRIES = 3;
/**
 * Delay before `start()` retries an HTTP 529 (cluster overload) when the
 * client's own retries are disabled (`maxRetries: 0`). Otherwise the client
 * already retried the 529, honoring the API's `Retry-After`.
 */
export const CLUSTER_OVERLOAD_RETRY_DELAY_MS = 30_000;
/** @deprecated Legacy request limit; CAPTCHA polls now use at most 10 seconds per request. */
export const CAPTCHA_SOLVE_TIMEOUT_MS = 100_000;

export type PerceptionType = NonNullable<ObserveRequest['perception_type']>;

/** Migration guide for the observe options removed on December 1, 2026. */
const OBSERVE_MIGRATION_URL = 'https://docs.notte.cc/features/sessions/observe-migration';
const OBSERVE_DEPRECATIONS = {
  instructions: `\`observe({ instructions })\` is deprecated and will be removed on December 1, 2026; <<ALTERNATIVE FOR instructions: session.act() — pending>>. See ${OBSERVE_MIGRATION_URL}`,
  deep: `\`perception_type: 'deep'\` is deprecated and will be removed on December 1, 2026; use \`perception_type: 'fast'\` (the default). See ${OBSERVE_MIGRATION_URL}`,
} as const;

export type SessionCloseReason = 'manual' | 'error';

export interface ExecuteOptions {
  /** Throw when the action fails. Defaults to the session's `raiseOnFailure` (true). */
  raiseOnFailure?: boolean;
}

export interface ReplayOptions {
  /** Poll until the replay is ready instead of failing on 404. Defaults to true. */
  wait?: boolean;
  /** Maximum time to wait for the replay, in milliseconds. Defaults to 240 000. */
  timeoutMs?: number;
  /** Delay between polling attempts, in milliseconds. Defaults to 5 000. */
  pollIntervalMs?: number;
}

/** Target for `session.saveProfile()`. Pass at most one of the two fields. */
export interface SaveProfileOptions {
  /** Existing profile to overwrite with the session's current browser state. */
  profile_id?: string;
  /** Create a new profile with this name and save into it. */
  name?: string;
}

export interface SessionScriptOptions {
  /** Return a standalone workflow script rather than only the relevant steps. Defaults to true. */
  as_workflow?: boolean;
  /** Infer a `response_format` schema for scrape calls that have instructions but no schema. */
  infer_response_format?: boolean;
}

export interface SessionStartOptions extends AuthWaitOptions {
  /** Override the session default; false returns while authentication continues. */
  wait_for_authentication?: boolean;
}

export interface SessionOptions extends ApiSessionStartRequest {
  /** Wait in the SDK for managed authentication on start(). Defaults to true; use() always waits. */
  wait_for_authentication?: boolean;
  /** Additional server-side login attempts, from 0 to 2. Only sent with auth_ids. */
  auth_retry?: number;
  /**
   * @deprecated Remote sessions always use the supported browser launch mode.
   * Retained as a boolean so existing typed configuration still compiles.
   * `true` is discarded; `false` raises a migration error when starting.
   */
  headless?: boolean;
  /**
   * Open the live viewer in the local default browser after the session starts.
   * This is a local SDK option and is not sent to the API.
   */
  open_viewer?: boolean;
  /**
   * Default for `execute()`: throw `ActionExecutionError` when an action fails.
   * The counterpart of `raise_on_failure` on `RemoteSession`. Defaults to true.
   */
  raiseOnFailure?: boolean;
  /**
   * Default perception type for `observe()`. Defaults to `fast`. `'deep'` is
   * deprecated and removed on December 1, 2026; use `'fast'`.
   */
  perception_type?: PerceptionType;
  /**
   * JSON cookie file: loaded into the session on `start()` when it exists and
   * appended with the session cookies on `stop()`.
   */
  cookie_file?: string;
  /** File storage to attach to the session for uploads and downloads. */
  storage?: RemoteFileStorage;
}

/**
 * Keep the external CDP client from competing with Notte for native dialogs.
 *
 * Playwright automatically handles a JavaScript dialog when no listener is
 * registered. Native dialogs are target-global, so that default races the
 * Notte browser controller attached to the same target. The backend owns
 * dialog handling; this listener makes the SDK Playwright connection an
 * observer without issuing a second `Page.handleJavaScriptDialog` command.
 */
export function observeServerOwnedDialog(_dialog: Dialog): void {}

export function installServerOwnedDialogPolicy(browser: Pick<Browser, 'contexts'>): void {
  for (const context of browser.contexts() as BrowserContext[]) {
    context.on('dialog', observeServerOwnedDialog);
  }
}

const NETWORK_URL_SCHEMES = new Set(['http', 'https', 'ws', 'wss']);

/** Keep only a network origin or a safe browser page name in lifecycle logs. */
export function redactPlaywrightUrl(url: string): string {
  const scheme = /^([a-zA-Z][a-zA-Z0-9+.-]*):/.exec(url)?.[1]?.toLowerCase();
  if (!scheme) return '<redacted>';
  if (scheme === 'about') {
    const pageName = url.slice(url.indexOf(':') + 1).split(/[?#]/, 1)[0].toLowerCase();
    return pageName === 'blank' || pageName === 'srcdoc' ? `about:${pageName}` : 'about:';
  }
  if (scheme === 'file') return 'file:';
  if (!NETWORK_URL_SCHEMES.has(scheme)) return `${scheme}:`;
  try {
    const parsed = new URL(url);
    return `${scheme}://${parsed.host}`;
  } catch {
    return '<unparseable>';
  }
}

const fallbackObjectIds = new WeakMap<object, string>();
let nextFallbackObjectId = 0;

/** Best-effort stable identity for a Playwright object. */
function playwrightObjectId(value: object): string {
  try {
    const guid = (value as { _guid?: unknown })._guid;
    if (typeof guid === 'string') return guid;
  } catch {
    // Fall through to a local id.
  }
  let id = fallbackObjectIds.get(value);
  if (id === undefined) {
    id = `object@${++nextFallbackObjectId}`;
    fallbackObjectIds.set(value, id);
  }
  return id;
}

function describeError(error: unknown): string {
  return error instanceof Error ? `${error.name}: ${error.message}` : String(error);
}

type PlaywrightState = Record<string, unknown>;

function playwrightPageState(page: Page): PlaywrightState {
  const state: PlaywrightState = { page_id: playwrightObjectId(page) };
  try {
    state.url = redactPlaywrightUrl(page.url());
  } catch (error) {
    state.url_error = describeError(error);
  }
  try {
    state.is_closed = page.isClosed();
  } catch (error) {
    state.is_closed_error = describeError(error);
  }
  return state;
}

interface PlaywrightEventOptions {
  browser: Browser;
  cachedPage: Page | null;
  observedPage?: Page;
  observedContext?: BrowserContext;
  level?: Exclude<LogMethod, 'error'>;
}

/**
 * Browser session created with `client.Session(options)`.
 * Call `start()` before using it and `stop()` when finished, or use `use()`
 * to start and stop automatically around an asynchronous callback.
 */
export class Session {
  private client: NotteClient;
  private options: ApiSessionStartRequest & { use_file_storage?: boolean };
  private openViewer: boolean;
  private legacyHeadless: boolean | undefined;
  private defaultRaiseOnFailure: boolean;
  private defaultPerceptionType: PerceptionType;
  private readonly warnedObserveDeprecations = new Set<keyof typeof OBSERVE_DEPRECATIONS>();
  private cookieFile: string | undefined;
  private cookiesLoaded = false;
  private cookieLoadPromise: Promise<void> | undefined;
  private authenticationReady = false;
  private fileStorage: RemoteFileStorage | undefined;
  private sessionId: string | null = null;
  private isActive = false;
  private response: SessionResponse | null = null;
  private playwrightBrowser: Browser | null = null;
  private playwrightPage: Page | null = null;
  private playwrightLogger: Logger | undefined;
  private playwrightConnectionGeneration = 0;
  private playwrightObserved = new WeakSet<object>();
  private playwrightCleanupInProgress = false;

  constructor(client: NotteClient, options: SessionOptions = {}) {
    this.client = client;
    const {
      open_viewer = false,
      headless,
      raiseOnFailure = true,
      perception_type = 'fast',
      cookie_file,
      storage,
      ...sessionOptions
    } = options;
    this.options = storage ? { ...sessionOptions, use_file_storage: true } : sessionOptions;
    this.openViewer = open_viewer;
    this.legacyHeadless = headless;
    this.defaultRaiseOnFailure = raiseOnFailure;
    this.defaultPerceptionType = perception_type;
    this.cookieFile = cookie_file;
    this.fileStorage = storage;
  }

  // #######################################################################
  // ############################# Session #################################
  // #######################################################################

  /**
   * Start the session: creates a new session on the server.
   *
   * 503, 529, and refused connections follow the client's retry policy
   * (`NotteClientConfig.maxRetries`, honoring `Retry-After`). Other 5xx
   * errors are retried up to `SESSION_START_TRIES` times. With client
   * retries disabled, 529 waits `CLUSTER_OVERLOAD_RETRY_DELAY_MS` instead.
   * 4xx errors are never retried.
   *
   * Managed-auth sessions wait for readiness by default. Pass
   * `{ wait_for_authentication: false }` for an explicit nonblocking start,
   * then call `waitForAuth()` before executing actions or connecting over CDP.
   * Cancellation during creation waits for its response so the new session can
   * be closed. Cancellation or failure during the startup wait also closes it.
   * Prefer `session.use(async session => { ... })`, which also stops the session.
   * @example
   * const session = client.Session();
   * await session.start();
   */
  async start(options: SessionStartOptions = {}): Promise<void> {
    if (this.legacyHeadless === true) {
      console.warn('`headless: true` is deprecated and ignored; remote sessions always use the supported browser launch mode.');
      this.legacyHeadless = undefined;
    }
    if (this.isActive) {
      throw new Error('Session is already active');
    }

    options.signal?.throwIfAborted();
    const { auth_retry, wait_for_authentication, ...request } = this.options;
    const body = {
      ...request,
      ...(this.legacyHeadless !== undefined ? { headless: this.legacyHeadless } : {}),
      ...(auth_retry !== undefined ? { auth_retry } : {}),
      ...(request.auth_ids?.length ? { wait_for_authentication: false } : {}),
    };
    const shouldWait = options.wait_for_authentication ?? wait_for_authentication ?? true;
    // The client's retry policy (503, 529, refused connections) is applied
    // here instead of in the transport, so the caller's signal interrupts the
    // wait between attempts without cancelling a creation already in flight.
    const maxRetries = this.client.getConfig().maxRetries ?? 0;
    const timeoutMs = this.client.getConfig().timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;
    const deadline = timeoutMs > 0 ? Date.now() + timeoutMs : undefined;
    const fitsDeadline = (wait: number) => deadline === undefined || Date.now() + wait < deadline;
    let transientRetries = 0;
    let tries = SESSION_START_TRIES;
    const origTries = tries;
    let sessionData: SessionResponse | undefined;
    while (tries > 0) {
      options.signal?.throwIfAborted();
      if (!fitsDeadline(0)) throw new NotteTimeoutError(`Session start timed out after ${timeoutMs}ms`);
      try {
        const response = await sessionStart({
          client: this.client.getClient(), body, throwOnError: true, headers: {
            [MAX_RETRIES_HEADER]: '0',
            ...(deadline === undefined ? {} : { [TIMEOUT_HEADER]: String(Math.max(1, deadline - Date.now())) }),
          },
        });
        sessionData = response.data;
        break;
      } catch (error) {
        const transient = error instanceof NotteAPIError
          ? isRetryableStatus(error.statusCode, 'POST')
          : isRetryableNetworkError(error, 'POST');
        if (maxRetries > 0 && transient) {
          const wait = transientRetries >= maxRetries ? undefined : error instanceof NotteAPIError
            ? retryDelayMs(transientRetries, error.response?.headers.get('retry-after'))
            : backoffDelayMs(transientRetries);
          if (wait === undefined || !fitsDeadline(wait)) throw error;
          transientRetries += 1;
          console.warn(
            `Failed to start session (${error instanceof NotteAPIError ? error.statusCode : 'connection error'}), retrying in ${(wait / 1000).toFixed(1)}s (${transientRetries}/${maxRetries})`
          );
          await pauseStart(wait, options.signal);
          continue;
        }
        tries -= 1;
        // raise if no tries left, if the error is not an API error, or if it is a 4xx
        if (tries === 0 || !(error instanceof NotteAPIError) || error.statusCode < 500) {
          throw error;
        }
        const retryStr = `${origTries - tries}/${origTries - 1}`;
        if (!fitsDeadline(error.statusCode === 529 ? CLUSTER_OVERLOAD_RETRY_DELAY_MS : 0)) throw error;
        if (error.statusCode === 529) {
          console.warn(
            `Failed to start session due to cluster overload, retrying in ${CLUSTER_OVERLOAD_RETRY_DELAY_MS / 1000} seconds (${retryStr})...`
          );
          await pauseStart(CLUSTER_OVERLOAD_RETRY_DELAY_MS, options.signal);
        } else {
          console.warn(`Failed to start session: retrying (${retryStr})`);
        }
      }
    }
    if (!sessionData) {
      throw new Error('Failed to start session: empty response');
    }

    this.sessionId = sessionData.session_id;
    this.isActive = true;
    this.playwrightCleanupInProgress = false;
    this.response = sessionData;
    this.cookiesLoaded = false;
    this.cookieLoadPromise = undefined;
    this.authenticationReady = false;
    // `forSession` clones a storage already bound to another session, so one
    // RemoteFileStorage reused across sessions never points at the wrong one.
    this.fileStorage = this.fileStorage?.forSession(sessionData.session_id);

    // The remote browser exists from here on: if any post-start step fails,
    // stop it before rethrowing so a bad cookie file cannot leak a session.
    try {
      options.signal?.throwIfAborted();
      if (!fitsDeadline(0)) throw new NotteTimeoutError(`Session start timed out after ${timeoutMs}ms`);
      if (shouldWait) await this.waitForAuth(options);
      if (this.openViewer) {
        this.openViewerInBrowser();
      }
      if (this.response?.status === 'active') await this.loadInitialCookies();
    } catch (error) {
      try {
        await this.stop('error');
      } catch (stopError) {
        console.error(`[Session] Failed to stop ${sessionData.session_id} after a start failure: ${String(stopError)}`);
      }
      throw error;
    }
  }

  /**
   * Wait for this session to become usable without creating a session or submitting another login.
   * A standalone wait leaves session ownership with the caller, including on timeout or cancellation.
   */
  async waitForAuth(options: AuthWaitOptions = {}): Promise<void> {
    options.signal?.throwIfAborted();
    if (!this.response) throw new Error('Session has not started');
    if (this.response.status === 'active') {
      await this.loadInitialCookies();
      return;
    }
    const sessionId = this.lastSessionId();
    this.response = await pollAuth(async signal => {
      const response = await sessionAuthReadiness({
        client: this.client.getClient(), path: { session_id: sessionId },
        headers: { [TIMEOUT_HEADER]: '10000' }, signal, throwOnError: true,
      });
      let result: typeof response.data | SessionResponse = response.data;
      if (result.status === 'active') {
        this.authenticationReady = true;
        result = (await sessionStatus({
          client: this.client.getClient(), path: { session_id: sessionId },
          headers: { [TIMEOUT_HEADER]: '10000' }, signal, throwOnError: true,
        })).data;
        this.authenticationReady = result.status === 'active';
        if (this.authenticationReady) return result as SessionResponse;
      }
      if (result.status !== 'authenticating') throw new ManagedAuthError(result.error || 'Session authentication failed');
      return undefined;
    }, options);
    await this.loadInitialCookies();
  }

  private async loadInitialCookies(): Promise<void> {
    if (this.cookiesLoaded || this.cookieFile === undefined) return;
    if (!this.cookieLoadPromise) {
      const cookieFile = this.cookieFile;
      this.cookieLoadPromise = (async () => {
        if (existsSync(cookieFile)) {
          console.info(`🍪 Automatically loading cookies from ${cookieFile}`);
          await this.setCookiesFromFile(cookieFile);
        } else {
          console.warn(`🍪 Cookie file ${cookieFile} not found, skipping cookie loading`);
        }
        this.cookiesLoaded = true;
      })();
    }
    const pending = this.cookieLoadPromise;
    try {
      await pending;
    } finally {
      if (this.cookieLoadPromise === pending) this.cookieLoadPromise = undefined;
    }
  }

  /**
   * Stop the session and clean up resources (including any Playwright
   * connection opened with `page()`). When a `cookie_file` was given, the
   * session cookies are appended to it first. A session the API reports as
   * already stopped is tolerated with a warning.
   *
   * @example
   * await session.stop();
   */
  async stop(closeReason: SessionCloseReason = 'manual'): Promise<void> {
    if (!this.isActive || !this.sessionId) {
      return;
    }
    const sessionId = this.sessionId;
    const cleanupWasInProgress = this.playwrightCleanupInProgress;
    this.logPlaywrightStopRequested();
    await this.closePlaywright();

    if (this.cookieFile !== undefined && (this.authenticationReady || this.response?.status === 'active')) {
      try {
        const cookies = await this.getCookies();
        await createOrAppendCookiesToFile(this.cookieFile, cookies);
      } catch (error) {
        console.error(`🍪 Error saving cookies to ${this.cookieFile}: ${String(error)}`);
      }
    }

    try {
      const response = await sessionStop({
        client: this.client.getClient(),
        path: { session_id: sessionId },
        query: { close_reason: closeReason },
        throwOnError: true,
      });
      if (response.data.status !== 'closed') {
        throw new Error(`[Session] ${sessionId} failed to stop`);
      }
      this.response = response.data;
    } catch (error) {
      const message = (error instanceof Error ? error.message : String(error)).toLowerCase();
      if (message.includes('already stopped') || message.includes('already closed')) {
        console.warn(`Session ${sessionId} was already stopped`);
      } else {
        // The session may still be alive: keep reporting its failures as warnings.
        this.playwrightCleanupInProgress = cleanupWasInProgress;
        throw error;
      }
    }
    this.isActive = false;
    this.sessionId = null;
  }

  private async closePlaywright(): Promise<void> {
    const browser = this.playwrightBrowser;
    if (!browser) {
      this.playwrightPage = null;
      return;
    }
    try {
      // Keep the cached page while closing so lifecycle logs can tell it apart from other tabs.
      await browser.close();
    } catch (error) {
      console.warn(`[Session] Failed to close the Playwright connection: ${String(error)}`);
    } finally {
      if (this.playwrightBrowser === browser) {
        this.playwrightBrowser = null;
        this.playwrightPage = null;
      }
    }
  }

  // #######################################################################
  // ###################### Playwright diagnostics #########################
  // #######################################################################

  private diagnosticsLogger(): Logger {
    this.playwrightLogger ??= new Logger(resolveLogLevel(this.client.getConfig().logLevel));
    return this.playwrightLogger;
  }

  private playwrightState(browser: Browser, cachedPage: Page | null): PlaywrightState {
    const state: PlaywrightState = {
      connection_generation: this.playwrightConnectionGeneration,
      cleanup_in_progress: this.playwrightCleanupInProgress,
      cached_page_id: cachedPage ? playwrightObjectId(cachedPage) : null,
      cached_page: cachedPage ? playwrightPageState(cachedPage) : null,
    };
    try {
      state.browser_connected = browser.isConnected();
    } catch (error) {
      state.browser_connected_error = describeError(error);
    }
    const contexts: PlaywrightState[] = [];
    try {
      for (const context of browser.contexts()) {
        const contextState: PlaywrightState = { context_id: playwrightObjectId(context) };
        try {
          const pages = context.pages();
          contextState.pages = pages.map(playwrightPageState);
          contextState.contains_cached_page = cachedPage !== null && pages.includes(cachedPage);
        } catch (error) {
          contextState.pages_error = describeError(error);
        }
        contexts.push(contextState);
      }
    } catch (error) {
      state.contexts_error = describeError(error);
    }
    state.contexts = contexts;
    return state;
  }

  private logPlaywrightEvent(event: string, options: PlaywrightEventOptions): void {
    let level: LogMethod = options.level ?? 'warn';
    if (this.playwrightCleanupInProgress && event !== 'sdk_playwright_session_stop_requested') {
      // Closes and disconnects caused by the SDK's own cleanup are expected, not failures.
      level = 'debug';
    }
    const logger = this.diagnosticsLogger();
    if (!logger.isEnabled(level)) return;
    const details = this.playwrightState(options.browser, options.cachedPage);
    if (options.observedPage) details.observed_page = playwrightPageState(options.observedPage);
    if (options.observedContext) details.observed_context_id = playwrightObjectId(options.observedContext);
    const sessionId = this.sessionId ?? this.response?.session_id ?? 'unknown';
    logger.log(level, `[Session Playwright] ${event}: session=${sessionId} state=${JSON.stringify(details)}`);
  }

  /** Snapshot Playwright state before the SDK starts its own cleanup. */
  private logPlaywrightStopRequested(): void {
    if (this.playwrightBrowser) {
      this.logPlaywrightEvent('sdk_playwright_session_stop_requested', {
        browser: this.playwrightBrowser,
        cachedPage: this.playwrightPage,
        level: 'info',
      });
    }
    this.playwrightCleanupInProgress = true;
  }

  private logUnhealthyCachedPlaywrightPage(browser: Browser, page: Page): void {
    let unhealthy: boolean;
    try {
      unhealthy = !browser.isConnected() || page.isClosed() || !browser.contexts().some(context => context.pages().includes(page));
    } catch {
      unhealthy = true;
    }
    if (unhealthy) {
      this.logPlaywrightEvent('sdk_playwright_cached_page_unhealthy', { browser, cachedPage: page });
    }
  }

  private observePlaywrightPage(browser: Browser, page: Page): void {
    if (this.playwrightObserved.has(page)) return;
    this.playwrightObserved.add(page);
    page.on('close', () => {
      const cachedPage = this.playwrightPage;
      this.logPlaywrightEvent('sdk_playwright_page_closed', {
        browser,
        cachedPage,
        observedPage: page,
        level: page === cachedPage ? 'warn' : 'info',
      });
    });
    page.on('crash', () => {
      this.logPlaywrightEvent('sdk_playwright_page_crashed', { browser, cachedPage: this.playwrightPage, observedPage: page });
    });
  }

  private observePlaywrightBrowser(browser: Browser): void {
    browser.on('disconnected', () => {
      this.logPlaywrightEvent('sdk_playwright_browser_disconnected', { browser, cachedPage: this.playwrightPage });
    });
    for (const context of browser.contexts()) {
      if (!this.playwrightObserved.has(context)) {
        this.playwrightObserved.add(context);
        context.on('page', page => {
          this.observePlaywrightPage(browser, page);
          this.logPlaywrightEvent('sdk_playwright_page_created', {
            browser,
            cachedPage: this.playwrightPage,
            observedPage: page,
            level: 'info',
          });
        });
        context.on('close', () => {
          this.logPlaywrightEvent('sdk_playwright_context_closed', {
            browser,
            cachedPage: this.playwrightPage,
            observedContext: context,
          });
        });
      }
      for (const page of context.pages()) {
        this.observePlaywrightPage(browser, page);
      }
    }
  }

  /**
   * Get the current status of the session. Like Python, this keeps working
   * after `stop()` (for example to read the recorded `steps`).
   *
   * @returns Current session metadata, including lifecycle status and recorded steps. Works after `stop()`.
   * @throws Error if this session has never been started.
   * @throws NotteAPIError if the status request fails.
   * @example
   * const status = await session.status();
   * console.log(status.status); // 'active'
   */
  async status(): Promise<SessionResponse> {
    const response = await sessionStatus({
      client: this.client.getClient(),
      path: { session_id: this.lastSessionId() },
      throwOnError: true,
    });
    return response.data;
  }

  /** Session ID while the session is active, `null` otherwise. */
  getId(): string | null {
    return this.sessionId;
  }

  /** Whether the session has been started and not stopped yet. */
  isSessionActive(): boolean {
    return this.isActive;
  }

  /** The last `SessionResponse` received from the API (start, stop or status). */
  getResponse(): SessionResponse | null {
    return this.response;
  }

  /** The file storage attached to the session, when one was given. */
  get storage(): RemoteFileStorage | undefined {
    return this.fileStorage;
  }

  private requireSessionId(): string {
    if (!this.sessionId) {
      throw new Error('Session not started');
    }
    return this.sessionId;
  }

  /** Session ID of the active session, or of the last one when it was stopped. */
  private lastSessionId(): string {
    const sessionId = this.sessionId ?? this.response?.session_id;
    if (!sessionId) {
      throw new Error('Session not started');
    }
    return sessionId;
  }

  /**
   * Open the live viewer for this session in the local default browser.
   * @throws If the session has not started or no viewer URL is available.
   */
  viewer(): void {
    this.requireSessionId();
    const viewerUrl = this.response?.viewer_url;
    if (!viewerUrl) {
      throw new Error('No viewer URL available for this session');
    }
    openBrowser(viewerUrl);
  }

  private openViewerInBrowser(): void {
    const viewerUrl = this.response?.viewer_url;
    if (!viewerUrl) {
      console.warn('[Session] No viewer URL available; session started without opening a viewer.');
      return;
    }
    openBrowser(viewerUrl);
  }

  /**
   * Get presigned URLs for the session replay. Recordings are finalized after
   * the session is closed, so by default this polls on 404 until the replay is
   * ready. It keeps working after `stop()`.
   *
   * Throws an `Error` when the API reports the session is still active and a
   * `NotteTimeoutError` when the replay is not ready within `timeoutMs`.
   * @example
   * await session.stop();
   * const replay = await session.replay();
   * console.log(replay.mp4_url);
   */
  async replay(options: ReplayOptions = {}): Promise<ReplayResponse> {
    const { wait = true, timeoutMs = 240_000, pollIntervalMs = 5_000 } = options;
    const sessionId = this.lastSessionId();
    const request = async (): Promise<ReplayResponse> => {
      const response = await sessionReplay({
        client: this.client.getClient(),
        path: { session_id: sessionId },
        throwOnError: true,
      });
      if (!response.data) {
        throw new Error('Failed to get session replay: empty response');
      }
      return response.data;
    };
    if (!wait) {
      return request();
    }

    const deadline = Date.now() + timeoutMs;
    for (;;) {
      try {
        return await request();
      } catch (error) {
        if (!(error instanceof NotteAPIError) || error.statusCode !== 404) {
          throw error;
        }
        // Stop can complete before the replay service observes the closure.
        // Only reject immediately while this client still considers it active.
        if (this.isActive && (error.apiMessage ?? '').includes('still active')) {
          throw new Error(`Session ${sessionId} is still active — close the session first to generate the replay.`, {
            cause: error,
          });
        }
        if (Date.now() + pollIntervalMs > deadline) {
          throw new NotteTimeoutError(`Replay for session ${sessionId} not ready within ${timeoutMs}ms`, { cause: error });
        }
        await sleep(pollIntervalMs);
      }
    }
  }

  /**
   * Download the MP4 replay to a local file, like `ReplayResponse.download()`
   * in Python. Resolves with the absolute path of the written file and throws
   * when the replay has no `mp4_url`.
   *
   * @example
   * await session.stop();
   * const file = await session.downloadReplay('session.mp4');
   */
  async downloadReplay(path = 'replay.mp4', options: ReplayOptions = {}): Promise<string> {
    const replay = await this.replay(options);
    if (!replay.mp4_url) {
      throw new Error('No mp4_url available for download');
    }
    const response = await fetch(replay.mp4_url);
    if (!response.ok) {
      throw new Error(`Failed to download replay: HTTP ${response.status}`);
    }
    const target = resolve(path);
    await writeFile(target, new Uint8Array(await response.arrayBuffer()));
    return target;
  }

  // #######################################################################
  // ############################# Cookies #################################
  // #######################################################################

  /**
   * Upload cookies to the session.
   *
   * @example
   * await session.setCookies([{ name: 'token', value: 'abc', domain: 'example.com', path: '/', httpOnly: false }]);
   */
  async setCookies(cookies: Cookie[]): Promise<ExecutionResponse> {
    const response = await sessionCookiesSet({
      client: this.client.getClient(),
      path: { session_id: this.requireSessionId() },
      body: { cookies },
      throwOnError: true,
    });
    return response.data;
  }

  /**
   * Upload cookies from a JSON file (a list of cookies, like `getCookies()` returns).
   *
   * @example
   * await session.setCookiesFromFile('cookies.json');
   */
  async setCookiesFromFile(cookieFile: string): Promise<ExecutionResponse> {
    return this.setCookies(await readCookiesFile(cookieFile));
  }

  /**
   * Get the cookies of the session.
   *
   * @example
   * const cookies = await session.getCookies();
   * await fs.writeFile('cookies.json', JSON.stringify(cookies));
   */
  async getCookies(): Promise<Cookie[]> {
    const response = await sessionCookiesGet({
      client: this.client.getClient(),
      path: { session_id: this.requireSessionId() },
      throwOnError: true,
    });
    return response.data.cookies;
  }

  // #######################################################################
  // ############################# Profiles ################################
  // #######################################################################

  /**
   * Save the session's current browser state (cookies, localStorage, sessionStorage) into a
   * profile, without stopping the session.
   *
   * Pass `profile_id` to overwrite an existing profile or `name` to create a new one. With
   * neither, the state is saved into the profile the session was started with. The session's
   * start-time profile settings are not changed, so a session started with `persist: true`
   * still saves again when it stops.
   *
   * See [Browser Profiles](/features/sessions/browser-profiles) for the tested Python and TypeScript example.
   */
  async saveProfile(options: SaveProfileOptions = {}): Promise<ProfileResponse> {
    const { profile_id, name } = options;
    if (profile_id !== undefined && name !== undefined) {
      throw new Error('profile_id and name are mutually exclusive');
    }
    if (profile_id !== undefined && profile_id.trim() === '') {
      throw new Error('profile_id must not be empty');
    }
    if (name !== undefined && name.trim() === '') {
      throw new Error('name must not be empty');
    }
    const body: { profile_id?: string; name?: string } = {};
    if (profile_id !== undefined) body.profile_id = profile_id;
    if (name !== undefined) body.name = name;
    const response = await sessionProfileSave({
      client: this.client.getClient(),
      path: { session_id: this.requireSessionId() },
      body,
      throwOnError: true,
    });
    return response.data;
  }

  // #######################################################################
  // ############################# Debug / CDP #############################
  // #######################################################################

  /** Detailed debug information for the session (debug URL, websocket URLs, tabs). */
  async debugInfo(): Promise<SessionDebugResponse> {
    const response = await sessionDebugInfo({
      client: this.client.getClient(),
      path: { session_id: this.requireSessionId() },
      throwOnError: true,
    });
    return response.data;
  }

  /**
   * Debug information for one tab of the session. The API client has no
   * dedicated tab endpoint, so this reads the tab from `debugInfo().tabs`.
   */
  async debugTabInfo(tabIdx = 0): Promise<TabSessionDebugResponse> {
    const debug = await this.debugInfo();
    const tab = debug.tabs[tabIdx];
    if (!tab) {
      throw new Error(`Tab ${tabIdx} not found: the session has ${debug.tabs.length} tab(s)`);
    }
    return tab;
  }

  /**
   * Get the Chrome DevTools Protocol WebSocket URL for the session.
   *
   * A `cdp_url` given at construction (another browser provider) is returned
   * untouched. Notte-served URLs, from the start response or the debug info,
   * carry the database preview branch when one is configured.
   *
   * @returns The CDP WebSocket URL for connecting a browser automation client.
   * @throws Error if no session ID or CDP URL is available.
   * @example
   * const browser = await chromium.connectOverCDP(await session.cdpUrl());
   */
  async cdpUrl(): Promise<string> {
    if (!this.response) {
      throw new Error('Session not started');
    }
    if (this.options.cdp_url) {
      // cdp url from another session provider. It is handed to us by the
      // caller and served by someone else, so it gets no preview selector.
      return this.options.cdp_url;
    }
    // The remaining urls are websocket endpoints on our own API, which reads
    // the preview branch from the query string. Without it the handshake is
    // served from the default database and rejects a preview-branch session.
    if (this.response.cdp_url) {
      return this.client.withDbPreview(this.response.cdp_url);
    }
    const debug = await this.debugInfo();
    return this.client.withDbPreview(debug.ws.cdp);
  }

  /**
   * Get a Playwright page connected to the session via CDP. The connection is
   * established lazily on first access, cached, and closed by `stop()`.
   * Native dialogs are left to the Notte backend.
   *
   * Requires the optional `playwright-core` peer dependency
   * (`npm install playwright-core`).
   *
   * @example
   * const page = await session.page();
   * await page.goto('https://www.google.com');
   * await page.screenshot({ path: 'screenshot.png' });
   */
  async page(): Promise<Page> {
    if (this.playwrightPage) {
      if (this.playwrightBrowser) {
        this.logUnhealthyCachedPlaywrightPage(this.playwrightBrowser, this.playwrightPage);
      }
      return this.playwrightPage;
    }
    let playwright: typeof import('playwright-core');
    try {
      playwright = await import('playwright-core');
    } catch (error) {
      throw new Error('Playwright not installed. Run `npm install playwright-core` to use `session.page()`.', {
        cause: error,
      });
    }
    try {
      let connected = false;
      if (!this.playwrightBrowser) {
        const cdpUrl = await this.cdpUrl();
        // Identify the SDK to Notte's CDP endpoint, as every API call does; a caller's
        // own browser (`cdp_url` option) gets nothing extra.
        this.playwrightBrowser = this.options.cdp_url
          ? await playwright.chromium.connectOverCDP(cdpUrl)
          : await playwright.chromium.connectOverCDP(cdpUrl, {
              headers: { 'x-notte-request-origin': REQUEST_ORIGIN, 'x-notte-sdk-version': SDK_VERSION },
            });
        installServerOwnedDialogPolicy(this.playwrightBrowser);
        this.playwrightConnectionGeneration += 1;
        this.observePlaywrightBrowser(this.playwrightBrowser);
        connected = true;
      }
      const page = this.playwrightBrowser.contexts()[0]?.pages()[0];
      if (!page) {
        throw new Error('the browser has no open page');
      }
      this.playwrightPage = page;
      if (connected) {
        this.logPlaywrightEvent('sdk_playwright_connected', { browser: this.playwrightBrowser, cachedPage: page, level: 'info' });
      }
      return page;
    } catch (error) {
      throw new Error(`Failed to access the playwright page from CDP: ${error instanceof Error ? error.message : String(error)}`, {
        cause: error,
      });
    }
  }

  /**
   * Get the workflow code generated from the session steps
   * (`GET /sessions/{id}/workflow/code`).
   *
   * @example
   * const { python_script } = await session.getScript();
   */
  async getScript(options: SessionScriptOptions = {}): Promise<AgentFunctionCodeResponse> {
    const { as_workflow = true, infer_response_format } = options;
    const response = await getSessionScript({
      client: this.client.getClient(),
      path: { session_id: this.lastSessionId() },
      query: { as_workflow, ...(infer_response_format === undefined ? {} : { infer_response_format }) },
      throwOnError: true,
    });
    return response.data;
  }

  // #######################################################################
  // ############################# Page ####################################
  // #######################################################################

  /**
   * Execute an action on the current page.
   *
   * When the action fails and `raiseOnFailure` is true (the default, see the
   * session option), the structured `exception_detail` returned by the API is
   * rehydrated into an `ActionExecutionError` whose `errorType` names the
   * server-side error class. `captcha_solve` actions get a 100 s request
   * timeout and are retried up to 3 times on HTTP 408.
   *
   * @param action - Action type, target, and action-specific arguments.
   * @param options - Override failure handling for this call; otherwise use the session setting.
   * @returns The execution response, including `success` and failure details when throwing is disabled.
   * @throws ActionExecutionError if the action fails and failure throwing is enabled.
   * @throws NotteAPIError if the API request fails.
   * @example
   * import { actions } from 'notte-sdk';
   *
   * await session.execute({ type: 'goto', url: 'https://www.notte.cc' });
   * await session.execute(actions.fill({ selector: "input[name='email']", value: 'user@example.com' }));
   * const result = await session.execute({ type: 'click', id: 'B1' }, { raiseOnFailure: false });
   * if (!result.success) console.log(result.message);
   */
  async execute(action: ExecuteAction, options: boolean | ExecuteOptions = {}): Promise<CaptchaExecutionResponse> {
    const sessionId = this.requireSessionId();
    const raiseOnFailure =
      typeof options === 'boolean' ? options : (options.raiseOnFailure ?? this.defaultRaiseOnFailure);
    const result = await executeWithCaptcha(action, this.client.getConfig().captchaTimeoutSeconds ?? 180,
      async (requestAction, params, timeoutMs) => {
        const query: typeof params & NonNullable<PageExecuteData['query']> = params;
        const response = await pageExecute({
          client: this.client.getClient(), path: { session_id: sessionId }, body: requestAction,
          query, headers: timeoutMs === undefined ? undefined : { [TIMEOUT_HEADER]: String(timeoutMs) },
          throwOnError: true,
        });
        return response.data;
      });

    // Gate on "did the action fail", not "did something throw", to mirror the local session.
    if (raiseOnFailure && !result.success) {
      console.error(`🚨 Execution failed with message: '${result.message}'`);
      if (result.exception_detail) {
        // The structured wire payload carries the concrete error type, messages and flags.
        throw new ActionExecutionError(result.exception_detail);
      }
      // An API build that predates `exception_detail` may report a failure without
      // an exception; the message is all the caller has to go on.
      const fallbackMessage = String(result.message ?? '').trim() || `Failed to execute action: ${action.type}`;
      throw ActionExecutionError.fromMessage(fallbackMessage);
    }
    return result;
  }

  /**
   * Evaluate JavaScript on the current page and return its result as a string.
   *
   * The result is stringified the way `evaluate_js` records it: objects and
   * arrays as JSON, a JS `null` as the string `"null"`. On failure the typed
   * `ActionExecutionError` is thrown with the actual JavaScript error; pass
   * `raiseOnFailure: false` to get the execution result envelope instead.
   *
   * @example
   * const title = await session.evaluateJs('document.title');
   * const payload = JSON.parse(await session.evaluateJs('(async () => JSON.stringify(await (await fetch("/api")).json()))()'));
   */
  async evaluateJs(code: string, options?: { raiseOnFailure?: true }): Promise<string>;
  async evaluateJs(code: string, options: { raiseOnFailure: false }): Promise<ApiExecutionResponse>;
  async evaluateJs(code: string, options: ExecuteOptions = {}): Promise<string | ApiExecutionResponse> {
    const raiseOnFailure = options.raiseOnFailure ?? true;
    const result = await this.execute({ type: 'evaluate_js', code }, { raiseOnFailure });
    if (!raiseOnFailure) {
      return result;
    }
    if (!result.data) {
      // an API build that predates the eval-js fix reports success without data
      throw new EvaluateJsNoDataError();
    }
    return result.data.markdown;
  }

  /**
   * Issue an HTTP request from the page the session is on and return the response.
   *
   * The request runs inside the browser through `fetch()`, so it carries the
   * page's cookies, the session's proxy and the browser's own network
   * fingerprint. A relative `url` resolves against the current page, which
   * also makes it same-origin; a cross-origin URL is subject to CORS exactly
   * as in a browser tab, so `goto` the target origin first. Redirects are
   * followed and the final URL is on `response.url`. A non-2xx status is
   * returned, not thrown; `response.raiseForStatus()` throws `PageFetchHTTPError`.
   *
   * `json` is serialised as the body with an `application/json` content type,
   * `data` as a form body when it is an object or verbatim when it is a string.
   *
   * @param url - Absolute URL or a path relative to the current page.
   * @param options - HTTP method, headers, and request body settings.
   * @returns A response with status, headers, and body readers. Non-2xx responses are not automatically thrown.
   * @throws ActionExecutionError if browser-side execution fails.
   * @example
   * await session.execute({ type: 'goto', url: 'https://en.wikipedia.org/wiki/Main_Page' });
   * const summary = await (await session.fetch('/api/rest_v1/page/summary/Main_Page')).json();
   */
  async fetch(url: string, options: PageFetchOptions = {}): Promise<PageFetchResponse> {
    const script = buildFetchScript(url, options);
    return responseFromEvaluated(await this.evaluateJs(script));
  }

  /**
   * Observe the current page: the list of actions that can be taken, a
   * screenshot and page metadata.
   *
   * The `perception_type` defaults to the session option (`fast`). A bare
   * string argument is accepted as the perception type.
   *
   * Deprecated: `perception_type: 'deep'` and `instructions` are removed on
   * December 1, 2026, and each warns once per session. Use `perception_type:
   * 'fast'` (the default) instead of `'deep'`. For `instructions`:
   * `<<ALTERNATIVE FOR instructions: session.act() — pending>>`. See https://docs.notte.cc/features/sessions/observe-migration
   *
   * @param options - Observation settings, including an optional URL, or a perception-mode string.
   * @returns Structured page analysis, available actions, and page metadata.
   * @throws NotteAPIError if observation fails.
   * @example
   * const obs = await session.observe();
   * console.log(obs.space.description);
   * const firstActions = await session.observe({ max_nb_actions: 50 });
   */
  async observe(options: ObserveRequest | PerceptionType = {}): Promise<Observation> {
    const body: ObserveRequest = typeof options === 'string' ? { perception_type: options } : { ...options };
    if (body.perception_type == null) {
      body.perception_type = this.defaultPerceptionType;
    }
    if (body.instructions != null) {
      this.warnObserveDeprecation('instructions');
    }
    if (body.perception_type !== 'fast') {
      this.warnObserveDeprecation('deep');
    }
    const response = await pageObserve({
      client: this.client.getClient(),
      path: { session_id: this.requireSessionId() },
      body,
      throwOnError: true,
    });
    return response.data;
  }

  private warnObserveDeprecation(option: keyof typeof OBSERVE_DEPRECATIONS): void {
    if (!this.warnedObserveDeprecations.has(option)) {
      this.warnedObserveDeprecations.add(option);
      console.warn(OBSERVE_DEPRECATIONS[option]);
    }
  }

  /**
   * Scrape the current page.
   *
   * With `response_format` or `instructions`, the extracted data is returned
   * directly and a failed extraction throws `ScrapeFailedError`. Pass
   * `raiseOnFailure: false` to receive the `StructuredData` wrapper instead.
   * @example
   * const markdown = await session.scrape({ only_main_content: true });
   * const product = await session.scrape({ response_format: Product, instructions: 'Extract the product' });
   * const result = await session.scrape({ response_format: Product, raiseOnFailure: false });
   * if (result.success) console.log(result.data);
   */
  async scrape(options?: SessionScrapeOptions<unknown> & { response_format?: undefined; instructions?: undefined | null }): Promise<string>;
  async scrape<T>(options: SessionScrapeOptions<T> & { response_format: ZodLikeSchema<T>; raiseOnFailure?: true }): Promise<T>;
  async scrape<T>(options: SessionScrapeOptions<T> & { response_format: ZodLikeSchema<T>; raiseOnFailure: false }): Promise<StructuredData<T>>;
  async scrape(options: SessionScrapeOptions<unknown>): Promise<ScrapeResult<unknown>>;
  async scrape<T = unknown>(options: SessionScrapeOptions<T> = {}): Promise<ScrapeResult<T>> {
    const sessionId = this.requireSessionId();
    const body = await buildScrapeBody(options);
    const response = await pageScrape({
      client: this.client.getClient(),
      path: { session_id: sessionId },
      body: body as ScrapeRequest,
      throwOnError: true,
    });
    return processScrapeResponse<T>(response.data, options);
  }

  // #######################################################################
  // ############################# Lifecycle ###############################
  // #######################################################################

  /**
   * Context manager pattern: start the session, run the callback and stop the
   * session, with close reason `error` when the callback throws.
   *
   * Always waits for Managed Auth readiness before invoking the callback.
   *
   * @param callback - Async work to perform with the ready session.
   * @param options - Controls the Managed Auth readiness wait, including timeout and cancellation.
   * @returns The callback's return value after session cleanup has been attempted.
   * @throws Error if startup fails, the callback throws, or cleanup fails after a successful callback.
   * @example
   * await client.Session().use(async session => {
   *   await session.execute({ type: 'goto', url: 'https://www.notte.cc' });
   * });
   */
  async use<T>(callback: (session: Session) => Promise<T>, options: AuthWaitOptions = {}): Promise<T> {
    await this.start({ ...options, wait_for_authentication: true });
    let callbackFailed = false;
    try {
      return await callback(this);
    } catch (error) {
      callbackFailed = true;
      console.warn(`Session exiting because of exception: ${String(error)}`);
      throw error;
    } finally {
      try {
        await this.stop(callbackFailed ? 'error' : 'manual');
      } catch (stopError) {
        if (!callbackFailed) {
          throw stopError;
        }
        console.error('[Session] Failed to stop session after callback error:', stopError);
      }
    }
  }

  /**
   * Async iterator pattern for session lifecycle management.
   *
   * ```ts
   * for await (const session of client.Session()) {
   *   await session.execute({ type: 'goto', url: 'https://www.notte.cc' });
   * }
   * ```
   */
  async *[Symbol.asyncIterator]() {
    await this.start();
    try {
      yield this;
    } finally {
      await this.stop();
    }
  }
}

/** Wait between `start()` attempts; the caller's signal interrupts the wait. */
async function pauseStart(ms: number, signal: AbortSignal | undefined): Promise<void> {
  if (!signal) {
    await sleep(ms);
    return;
  }
  try {
    await delay(ms, undefined, { signal });
  } catch (error) {
    signal.throwIfAborted();
    throw error;
  }
}
