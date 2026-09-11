import { existsSync } from 'node:fs';
import { writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import type { Browser, BrowserContext, Dialog, Page } from 'playwright-core';
import { NotteClient, TIMEOUT_HEADER } from '@/client';
import type {
  AgentFunctionCodeResponse,
  ApiExecutionResponse,
  ApiSessionStartRequest,
  Cookie,
  ExecutionResponse,
  ImageData,
  Observation,
  ObserveRequest,
  ReplayResponse,
  ScrapeRequest,
  SessionDebugResponse,
  SessionResponse,
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
  sessionReplay,
  sessionStart,
  sessionStatus,
  sessionStop,
} from '@/lib/client/sdk.gen';
import { ActionExecutionError, EvaluateJsNoDataError, NotteAPIError, NotteTimeoutError, sleep } from '@/errors';
import { isCaptchaSolveAction, type ExecuteAction } from '@/actions';
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
import type { RemoteFileStorage } from '@/files';

/** Number of attempts `start()` makes on 5xx errors, like `RemoteSession.start(tries=3)`. */
export const SESSION_START_TRIES = 3;
/** Delay before retrying `start()` after an HTTP 529 (cluster overload). */
export const CLUSTER_OVERLOAD_RETRY_DELAY_MS = 30_000;
/** Request timeout for `captcha_solve` actions, like `PageClient.execute` in Python. */
export const CAPTCHA_SOLVE_TIMEOUT_MS = 100_000;
/** Number of attempts a `captcha_solve` action gets when the API answers 408. */
export const CAPTCHA_SOLVE_TRIES = 3;

export type PerceptionType = NonNullable<ObserveRequest['perception_type']>;
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

export interface SessionScriptOptions {
  /** Return a standalone workflow script rather than only the relevant steps. Defaults to true. */
  as_workflow?: boolean;
  /** Infer a `response_format` schema for scrape calls that have instructions but no schema. */
  infer_response_format?: boolean;
}

export interface SessionOptions extends ApiSessionStartRequest {
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
  /** Default perception type for `observe()`. Defaults to `fast`. */
  perception_type?: PerceptionType;
  /**
   * JSON cookie file: loaded into the session on `start()` when it exists and
   * appended with the session cookies on `stop()`.
   */
  cookie_file?: string;
  /** File storage to attach to the session so agents can consume uploaded files. */
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
  private cookieFile: string | undefined;
  private fileStorage: RemoteFileStorage | undefined;
  private sessionId: string | null = null;
  private isActive = false;
  private response: SessionResponse | null = null;
  private playwrightBrowser: Browser | null = null;
  private playwrightPage: Page | null = null;

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
   * Retries up to `SESSION_START_TRIES` times on 5xx errors, waiting
   * `CLUSTER_OVERLOAD_RETRY_DELAY_MS` on HTTP 529 (cluster overload). 4xx
   * errors are never retried.
   *
   * ```ts
   * const session = client.Session();
   * await session.start();
   * ```
   *
   * Prefer `session.use(async session => { ... })`, which also stops the session.
   */
  async start(): Promise<void> {
    if (this.legacyHeadless === false) {
      throw new Error(
        'Remote `headless: false` is no longer supported. `headless: true` sessions still include session replays and access to the live viewer.'
      );
    }
    if (this.legacyHeadless === true) {
      console.warn('`headless: true` is deprecated and ignored; remote sessions always use the supported browser launch mode.');
      this.legacyHeadless = undefined;
    }
    if (this.isActive) {
      throw new Error('Session is already active');
    }

    const body: ApiSessionStartRequest = this.options;
    let tries = SESSION_START_TRIES;
    const origTries = tries;
    let sessionData: SessionResponse | undefined;
    while (tries > 0) {
      tries -= 1;
      try {
        const response = await sessionStart({ client: this.client.getClient(), body, throwOnError: true });
        sessionData = response.data;
        break;
      } catch (error) {
        // raise if no tries left, if the error is not an API error, or if it is a 4xx
        if (tries === 0 || !(error instanceof NotteAPIError) || error.statusCode < 500) {
          throw error;
        }
        const retryStr = `${origTries - tries}/${origTries - 1}`;
        if (error.statusCode === 529) {
          console.warn(
            `Failed to start session due to cluster overload, retrying in ${CLUSTER_OVERLOAD_RETRY_DELAY_MS / 1000} seconds (${retryStr})...`
          );
          await sleep(CLUSTER_OVERLOAD_RETRY_DELAY_MS);
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
    this.response = sessionData;
    this.fileStorage?.setSessionId(sessionData.session_id);

    if (this.openViewer) {
      this.openViewerInBrowser();
    }
    if (this.cookieFile !== undefined) {
      if (existsSync(this.cookieFile)) {
        console.info(`🍪 Automatically loading cookies from ${this.cookieFile}`);
        await this.setCookiesFromFile(this.cookieFile);
      } else {
        console.warn(`🍪 Cookie file ${this.cookieFile} not found, skipping cookie loading`);
      }
    }
  }

  /**
   * Stop the session and clean up resources (including any Playwright
   * connection opened with `page()`). When a `cookie_file` was given, the
   * session cookies are appended to it first. A session the API reports as
   * already stopped is tolerated with a warning.
   *
   * ```ts
   * await session.stop();
   * ```
   */
  async stop(closeReason: SessionCloseReason = 'manual'): Promise<void> {
    if (!this.isActive || !this.sessionId) {
      return;
    }
    const sessionId = this.sessionId;
    await this.closePlaywright();

    if (this.cookieFile !== undefined) {
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
        throw error;
      }
    }
    this.isActive = false;
    this.sessionId = null;
  }

  private async closePlaywright(): Promise<void> {
    const browser = this.playwrightBrowser;
    this.playwrightBrowser = null;
    this.playwrightPage = null;
    if (browser) {
      try {
        await browser.close();
      } catch (error) {
        console.warn(`[Session] Failed to close the Playwright connection: ${String(error)}`);
      }
    }
  }

  /**
   * Get the current status of the session. Like Python, this keeps working
   * after `stop()` (for example to read the recorded `steps`).
   *
   * ```ts
   * const status = await session.status();
   * console.log(status.status); // 'active'
   * ```
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
   * ```ts
   * await session.stop();
   * const replay = await session.replay();
   * console.log(replay.mp4_url);
   * ```
   *
   * Throws an `Error` when the API reports the session is still active and a
   * `NotteTimeoutError` when the replay is not ready within `timeoutMs`.
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
        if ((error.apiMessage ?? '').includes('still active')) {
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
   * ```ts
   * await session.stop();
   * const file = await session.downloadReplay('session.mp4');
   * ```
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
   * ```ts
   * await session.setCookies([{ name: 'token', value: 'abc', domain: 'example.com', path: '/', httpOnly: false }]);
   * ```
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
   * ```ts
   * await session.setCookiesFromFile('cookies.json');
   * ```
   */
  async setCookiesFromFile(cookieFile: string): Promise<ExecutionResponse> {
    return this.setCookies(await readCookiesFile(cookieFile));
  }

  /**
   * Get the cookies of the session.
   *
   * ```ts
   * const cookies = await session.getCookies();
   * await fs.writeFile('cookies.json', JSON.stringify(cookies));
   * ```
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
   * ```ts
   * const browser = await chromium.connectOverCDP(await session.cdpUrl());
   * ```
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
   * ```ts
   * const page = await session.page();
   * await page.goto('https://www.google.com');
   * await page.screenshot({ path: 'screenshot.png' });
   * ```
   */
  async page(): Promise<Page> {
    if (this.playwrightPage) {
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
      if (!this.playwrightBrowser) {
        const cdpUrl = await this.cdpUrl();
        this.playwrightBrowser = await playwright.chromium.connectOverCDP(cdpUrl);
        installServerOwnedDialogPolicy(this.playwrightBrowser);
      }
      const page = this.playwrightBrowser.contexts()[0]?.pages()[0];
      if (!page) {
        throw new Error('the browser has no open page');
      }
      this.playwrightPage = page;
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
   * ```ts
   * const { python_script } = await session.getScript();
   * ```
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
   * ```ts
   * import { actions } from 'notte-sdk';
   *
   * await session.execute({ type: 'goto', url: 'https://www.notte.cc' });
   * await session.execute(actions.fill({ selector: "input[name='email']", value: 'user@example.com' }));
   * const result = await session.execute({ type: 'click', id: 'B1' }, { raiseOnFailure: false });
   * if (!result.success) console.log(result.message);
   * ```
   *
   * When the action fails and `raiseOnFailure` is true (the default, see the
   * session option), the structured `exception_detail` returned by the API is
   * rehydrated into an `ActionExecutionError` whose `errorType` names the
   * server-side error class. `captcha_solve` actions get a 100 s request
   * timeout and are retried up to 3 times on HTTP 408.
   */
  async execute(action: ExecuteAction, options: boolean | ExecuteOptions = {}): Promise<ApiExecutionResponse> {
    const sessionId = this.requireSessionId();
    const raiseOnFailure =
      typeof options === 'boolean' ? options : (options.raiseOnFailure ?? this.defaultRaiseOnFailure);
    const isCaptcha = isCaptchaSolveAction(action);

    let result: ApiExecutionResponse | undefined;
    for (let attempt = 0; attempt < CAPTCHA_SOLVE_TRIES; attempt += 1) {
      try {
        const response = await pageExecute({
          client: this.client.getClient(),
          path: { session_id: sessionId },
          body: action,
          headers: isCaptcha ? { [TIMEOUT_HEADER]: String(CAPTCHA_SOLVE_TIMEOUT_MS) } : undefined,
          throwOnError: true,
        });
        result = response.data;
        break;
      } catch (error) {
        if (isCaptcha && error instanceof NotteAPIError && error.statusCode === 408) {
          console.warn('Solve captcha action timed out. This can happen for long and complex captchas. Retrying...');
          continue;
        }
        throw error;
      }
    }
    if (!result) {
      throw new Error(`Failed to execute action '${action.type}'. This should not happen. Please report this issue.`);
    }

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
   * ```ts
   * const title = await session.evaluateJs('document.title');
   * const payload = JSON.parse(await session.evaluateJs('(async () => JSON.stringify(await (await fetch("/api")).json()))()'));
   * ```
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
   * ```ts
   * await session.execute({ type: 'goto', url: 'https://en.wikipedia.org/wiki/Main_Page' });
   * const summary = await (await session.fetch('/api/rest_v1/page/summary/Main_Page')).json();
   * ```
   */
  async fetch(url: string, options: PageFetchOptions = {}): Promise<PageFetchResponse> {
    const script = buildFetchScript(url, options);
    return responseFromEvaluated(await this.evaluateJs(script));
  }

  /**
   * Observe the current page: the list of actions that can be taken, a
   * screenshot and page metadata.
   *
   * ```ts
   * const obs = await session.observe();
   * console.log(obs.space.description);
   * const deep = await session.observe({ perception_type: 'deep', max_nb_actions: 50 });
   * ```
   *
   * The `perception_type` defaults to the session option (`fast`). A bare
   * string argument is accepted as the perception type.
   */
  async observe(options: ObserveRequest | PerceptionType = {}): Promise<Observation> {
    const body: ObserveRequest = typeof options === 'string' ? { perception_type: options } : { ...options };
    if (body.perception_type == null) {
      body.perception_type = this.defaultPerceptionType;
    }
    const response = await pageObserve({
      client: this.client.getClient(),
      path: { session_id: this.requireSessionId() },
      body,
      throwOnError: true,
    });
    return response.data;
  }

  /**
   * Scrape the current page.
   *
   * ```ts
   * const markdown = await session.scrape({ only_main_content: true });
   * const images = await session.scrape({ only_images: true });
   * const product = await session.scrape({ response_format: Product, instructions: 'Extract the product' });
   * const result = await session.scrape({ response_format: Product, raiseOnFailure: false });
   * if (result.success) console.log(result.data);
   * ```
   *
   * With `response_format` or `instructions`, the extracted data is returned
   * directly and a failed extraction throws `ScrapeFailedError`. Pass
   * `raiseOnFailure: false` to receive the `StructuredData` wrapper instead.
   */
  async scrape(options: SessionScrapeOptions<unknown> & { only_images: true }): Promise<ImageData[]>;
  async scrape(options?: SessionScrapeOptions<unknown> & { response_format?: undefined; instructions?: undefined | null; only_images?: false }): Promise<string>;
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
   * ```ts
   * await client.Session().use(async session => {
   *   await session.execute({ type: 'goto', url: 'https://www.notte.cc' });
   * });
   * ```
   */
  async use<T>(callback: (session: Session) => Promise<T>): Promise<T> {
    await this.start();
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
