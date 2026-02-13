// Client
export { NotteClient, type NotteClientOptions } from "./client.js";

// Sessions
export { SessionsClient } from "./sessions/sessions-client.js";
export {
  RemoteSession,
  type RemoteSessionOptions,
} from "./sessions/remote-session.js";

// Base
export { BaseClient, type BaseClientOptions } from "./base-client.js";
export { type NotteEndpoint } from "./endpoint.js";
export { withBody, withParams } from "./endpoint.js";

// Errors
export {
  NotteAPIError,
  AuthenticationError,
  InvalidRequestError,
} from "./errors.js";

// Version
export { SDK_VERSION } from "./version.js";

// Types & Schemas
export {
  // Cookie
  CookieSchema,
  SetCookiesRequestSchema,
  SetCookiesResponseSchema,
  GetCookiesResponseSchema,
  type Cookie,
  type SetCookiesRequest,
  type SetCookiesResponse,
  type GetCookiesResponse,
  // Session
  SessionStartRequestSchema,
  SessionResponseSchema,
  SessionListRequestSchema,
  type SessionStartRequest,
  type SessionResponse,
  type SessionListRequest,
  // Page
  ScrapeRequestSchema,
  ScrapeResponseSchema,
  ObserveRequestSchema,
  ObserveResponseSchema,
  ExecutionRequestSchema,
  ExecutionResponseSchema,
  type ScrapeRequest,
  type ScrapeResponse,
  type ObserveRequest,
  type ObserveResponse,
  type ExecutionRequest,
  type ExecutionResponse,
} from "./types/index.js";
