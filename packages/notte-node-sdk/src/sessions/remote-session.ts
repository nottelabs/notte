import type { SessionsClient } from "./sessions-client.js";
import type {
  SessionStartRequest,
  SessionResponse,
  ScrapeRequest,
  ScrapeResponse,
  ObserveRequest,
  ObserveResponse,
  ExecutionRequest,
  ExecutionResponse,
  Cookie,
  SetCookiesResponse,
  GetCookiesResponse,
} from "../types/index.js";

export interface RemoteSessionOptions extends SessionStartRequest {}

export class RemoteSession {
  private readonly client: SessionsClient;
  private readonly options: RemoteSessionOptions;
  private _sessionId: string | null = null;
  private _response: SessionResponse | null = null;
  private _stopped = false;

  constructor(client: SessionsClient, options: RemoteSessionOptions = {}) {
    this.client = client;
    this.options = options;
  }

  get sessionId(): string {
    if (!this._sessionId) {
      throw new Error(
        "Session has not been started. Call start() first.",
      );
    }
    return this._sessionId;
  }

  get response(): SessionResponse | null {
    return this._response;
  }

  get isStarted(): boolean {
    return this._sessionId !== null;
  }

  get isStopped(): boolean {
    return this._stopped;
  }

  async start(): Promise<SessionResponse> {
    if (this._sessionId) {
      throw new Error("Session already started");
    }
    this._response = await this.client.start(this.options);
    this._sessionId = this._response.session_id;
    return this._response;
  }

  async stop(): Promise<SessionResponse> {
    if (this._stopped) {
      return this._response!;
    }
    if (!this._sessionId) {
      throw new Error("Session has not been started");
    }
    this._response = await this.client.stop(this._sessionId);
    this._stopped = true;
    return this._response;
  }

  async status(): Promise<SessionResponse> {
    return this.client.status(this.sessionId);
  }

  async scrape(params?: ScrapeRequest): Promise<ScrapeResponse> {
    return this.client.scrape(this.sessionId, params);
  }

  async observe(params?: ObserveRequest): Promise<ObserveResponse> {
    return this.client.observe(this.sessionId, params);
  }

  async execute(action: ExecutionRequest): Promise<ExecutionResponse> {
    return this.client.execute(this.sessionId, action);
  }

  async setCookies(cookies: Cookie[]): Promise<SetCookiesResponse> {
    return this.client.setCookies(this.sessionId, cookies);
  }

  async getCookies(): Promise<GetCookiesResponse> {
    return this.client.getCookies(this.sessionId);
  }

  // --- Lifecycle helpers ---

  /**
   * Static helper for auto-cleanup. Works on all Node.js versions.
   *
   * ```ts
   * await RemoteSession.use(client, {}, async (session) => {
   *   await session.execute({ type: "goto", url: "https://example.com" });
   *   const data = await session.scrape();
   *   return data;
   * });
   * ```
   */
  static async use<T>(
    client: SessionsClient,
    options: RemoteSessionOptions,
    fn: (session: RemoteSession) => Promise<T>,
  ): Promise<T> {
    const session = new RemoteSession(client, options);
    await session.start();
    try {
      return await fn(session);
    } finally {
      await session.stop();
    }
  }

  /**
   * Attach to an existing session by ID (does not start a new one).
   */
  static fromId(
    client: SessionsClient,
    sessionId: string,
  ): RemoteSession {
    const session = new RemoteSession(client, {});
    session._sessionId = sessionId;
    return session;
  }

  // Symbol.asyncDispose for `await using` (Node 22+ / TypeScript 5.2+)
  async [Symbol.asyncDispose](): Promise<void> {
    if (this._sessionId && !this._stopped) {
      await this.stop();
    }
  }
}
