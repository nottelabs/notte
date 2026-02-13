import type { z } from "zod";
import type { NotteEndpoint } from "./endpoint.js";
import { AuthenticationError, NotteAPIError } from "./errors.js";
import { SDK_VERSION } from "./version.js";

export interface BaseClientOptions {
  apiKey?: string;
  serverUrl?: string;
  timeoutMs?: number;
}

export abstract class BaseClient {
  static readonly DEFAULT_SERVER_URL = "https://api.notte.cc";
  static readonly DEFAULT_TIMEOUT_MS = 60_000;

  readonly apiKey: string;
  readonly serverUrl: string;
  readonly timeoutMs: number;
  protected readonly baseEndpointPath: string | null;

  constructor(
    baseEndpointPath: string | null,
    options: BaseClientOptions = {},
  ) {
    const token =
      options.apiKey ??
      (typeof process !== "undefined" ? process.env.NOTTE_API_KEY : undefined);
    if (!token) {
      throw new AuthenticationError();
    }
    this.apiKey = token;
    this.serverUrl =
      options.serverUrl ??
      (typeof process !== "undefined"
        ? process.env.NOTTE_API_URL
        : undefined) ??
      BaseClient.DEFAULT_SERVER_URL;
    this.timeoutMs = options.timeoutMs ?? BaseClient.DEFAULT_TIMEOUT_MS;
    this.baseEndpointPath = baseEndpointPath;
  }

  protected getHeaders(): Record<string, string> {
    return {
      Authorization: `Bearer ${this.apiKey}`,
      "Content-Type": "application/json",
      "x-notte-sdk-version": SDK_VERSION,
      "x-notte-request-origin": "sdk",
    };
  }

  protected buildUrl(endpointPath: string): string {
    let base = this.serverUrl.replace(/\/+$/, "");
    if (this.baseEndpointPath) {
      base += "/" + this.baseEndpointPath.replace(/^\/+|\/+$/g, "");
    }
    const ep = endpointPath.replace(/^\/+/, "");
    return ep ? `${base}/${ep}` : base;
  }

  protected async rawRequest(
    endpoint: NotteEndpoint<unknown> & {
      body?: Record<string, unknown>;
      params?: Record<string, unknown>;
    },
  ): Promise<unknown> {
    const url = new URL(this.buildUrl(endpoint.path));
    if (endpoint.params) {
      for (const [k, v] of Object.entries(endpoint.params)) {
        if (v !== undefined && v !== null) {
          url.searchParams.set(k, String(v));
        }
      }
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);

    const init: RequestInit = {
      method: endpoint.method,
      headers: this.getHeaders(),
      signal: controller.signal,
    };

    if (
      (endpoint.method === "POST" || endpoint.method === "PATCH") &&
      endpoint.body
    ) {
      init.body = JSON.stringify(endpoint.body);
    }

    let response: Response;
    try {
      response = await fetch(url.toString(), init);
    } catch (err: unknown) {
      clearTimeout(timer);
      if (err instanceof DOMException && err.name === "AbortError") {
        throw new NotteAPIError(
          0,
          "Request timed out",
          endpoint.path,
        );
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }

    if (!response.ok) {
      let body: unknown;
      try {
        body = await response.json();
      } catch {
        body = await response.text();
      }
      throw new NotteAPIError(response.status, body, endpoint.path);
    }

    return response.json();
  }

  protected async request<T>(
    endpoint: NotteEndpoint<T> & {
      body?: Record<string, unknown>;
      params?: Record<string, unknown>;
    },
  ): Promise<T> {
    const raw = await this.rawRequest(endpoint);
    return endpoint.responseSchema.parse(raw);
  }

  protected async requestList<T>(
    endpoint: NotteEndpoint<T> & {
      body?: Record<string, unknown>;
      params?: Record<string, unknown>;
    },
  ): Promise<T[]> {
    const raw = await this.rawRequest(endpoint);
    let items: unknown[];
    if (Array.isArray(raw)) {
      items = raw;
    } else if (
      typeof raw === "object" &&
      raw !== null &&
      "items" in raw &&
      Array.isArray((raw as Record<string, unknown>).items)
    ) {
      items = (raw as Record<string, unknown>).items as unknown[];
    } else {
      throw new NotteAPIError(
        0,
        "Expected array or { items: [...] } response",
        endpoint.path,
      );
    }
    return items.map((item) => endpoint.responseSchema.parse(item));
  }

  async healthCheck(): Promise<void> {
    const url = `${this.serverUrl.replace(/\/+$/, "")}/health`;
    const response = await fetch(url, {
      headers: {
        "x-notte-sdk-version": SDK_VERSION,
        "x-notte-request-origin": "sdk",
      },
    });
    if (!response.ok) {
      throw new NotteAPIError(
        response.status,
        "Health check failed",
        "/health",
      );
    }
  }
}
