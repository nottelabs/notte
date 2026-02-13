import { BaseClient, type BaseClientOptions } from "../base-client.js";
import type { NotteEndpoint } from "../endpoint.js";
import {
  type GetCookiesResponse,
  GetCookiesResponseSchema,
  type SetCookiesResponse,
  SetCookiesResponseSchema,
  type SessionResponse,
  SessionResponseSchema,
  type SessionStartRequest,
  SessionStartRequestSchema,
  type SessionListRequest,
  SessionListRequestSchema,
  type ScrapeRequest,
  ScrapeRequestSchema,
  type ScrapeResponse,
  ScrapeResponseSchema,
  type ObserveRequest,
  ObserveRequestSchema,
  type ObserveResponse,
  ObserveResponseSchema,
  type ExecutionRequest,
  ExecutionRequestSchema,
  type ExecutionResponse,
  ExecutionResponseSchema,
  type Cookie,
} from "../types/index.js";

export class SessionsClient extends BaseClient {
  constructor(options: BaseClientOptions = {}) {
    super("sessions", options);
  }

  // --- Session lifecycle ---

  async start(params?: SessionStartRequest): Promise<SessionResponse> {
    const body = params
      ? SessionStartRequestSchema.parse(params)
      : {};
    const endpoint: NotteEndpoint<SessionResponse> & {
      body: Record<string, unknown>;
    } = {
      path: "start",
      method: "POST",
      responseSchema: SessionResponseSchema,
      body: body as Record<string, unknown>,
    };
    return this.request(endpoint);
  }

  async stop(sessionId: string): Promise<SessionResponse> {
    const endpoint: NotteEndpoint<SessionResponse> = {
      path: `${sessionId}/stop`,
      method: "DELETE",
      responseSchema: SessionResponseSchema,
    };
    return this.request(endpoint);
  }

  async status(sessionId: string): Promise<SessionResponse> {
    const endpoint: NotteEndpoint<SessionResponse> = {
      path: sessionId,
      method: "GET",
      responseSchema: SessionResponseSchema,
    };
    return this.request(endpoint);
  }

  async list(
    params?: SessionListRequest,
  ): Promise<SessionResponse[]> {
    const queryParams = params
      ? (SessionListRequestSchema.parse(params) as Record<string, unknown>)
      : undefined;
    const endpoint: NotteEndpoint<SessionResponse> & {
      params?: Record<string, unknown>;
    } = {
      path: "",
      method: "GET",
      responseSchema: SessionResponseSchema,
      params: queryParams,
    };
    return this.requestList(endpoint);
  }

  // --- Page operations ---

  async scrape(
    sessionId: string,
    params?: ScrapeRequest,
  ): Promise<ScrapeResponse> {
    const body = params
      ? (ScrapeRequestSchema.parse(params) as Record<string, unknown>)
      : {};
    const endpoint: NotteEndpoint<ScrapeResponse> & {
      body: Record<string, unknown>;
    } = {
      path: `${sessionId}/page/scrape`,
      method: "POST",
      responseSchema: ScrapeResponseSchema,
      body,
    };
    return this.request(endpoint);
  }

  async observe(
    sessionId: string,
    params?: ObserveRequest,
  ): Promise<ObserveResponse> {
    const body = params
      ? (ObserveRequestSchema.parse(params) as Record<string, unknown>)
      : {};
    const endpoint: NotteEndpoint<ObserveResponse> & {
      body: Record<string, unknown>;
    } = {
      path: `${sessionId}/page/observe`,
      method: "POST",
      responseSchema: ObserveResponseSchema,
      body,
    };
    return this.request(endpoint);
  }

  async execute(
    sessionId: string,
    action: ExecutionRequest,
  ): Promise<ExecutionResponse> {
    const body = ExecutionRequestSchema.parse(action) as Record<
      string,
      unknown
    >;
    const endpoint: NotteEndpoint<ExecutionResponse> & {
      body: Record<string, unknown>;
    } = {
      path: `${sessionId}/page/execute`,
      method: "POST",
      responseSchema: ExecutionResponseSchema,
      body,
    };
    return this.request(endpoint);
  }

  // --- Cookies ---

  async setCookies(
    sessionId: string,
    cookies: Cookie[],
  ): Promise<SetCookiesResponse> {
    const endpoint: NotteEndpoint<SetCookiesResponse> & {
      body: Record<string, unknown>;
    } = {
      path: `${sessionId}/cookies`,
      method: "POST",
      responseSchema: SetCookiesResponseSchema,
      body: { cookies },
    };
    return this.request(endpoint);
  }

  async getCookies(sessionId: string): Promise<GetCookiesResponse> {
    const endpoint: NotteEndpoint<GetCookiesResponse> = {
      path: `${sessionId}/cookies`,
      method: "GET",
      responseSchema: GetCookiesResponseSchema,
    };
    return this.request(endpoint);
  }
}
