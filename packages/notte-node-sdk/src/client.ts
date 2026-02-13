import type { BaseClientOptions } from "./base-client.js";
import { SessionsClient } from "./sessions/sessions-client.js";
import {
  RemoteSession,
  type RemoteSessionOptions,
} from "./sessions/remote-session.js";
import { SDK_VERSION } from "./version.js";

export interface NotteClientOptions extends BaseClientOptions {}

export class NotteClient {
  readonly sessions: SessionsClient;
  private readonly options: NotteClientOptions;

  constructor(options: NotteClientOptions = {}) {
    this.options = options;
    this.sessions = new SessionsClient(options);
  }

  /**
   * Create a RemoteSession (not yet started).
   * Call `.start()` or use `RemoteSession.use()` for auto-cleanup.
   */
  session(options: RemoteSessionOptions = {}): RemoteSession {
    return new RemoteSession(this.sessions, options);
  }

  async healthCheck(): Promise<void> {
    return this.sessions.healthCheck();
  }

  get version(): string {
    return SDK_VERSION;
  }
}
