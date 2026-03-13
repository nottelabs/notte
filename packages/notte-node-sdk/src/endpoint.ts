import type { z } from "zod";

export interface NotteEndpoint<T> {
  path: string;
  method: "GET" | "POST" | "DELETE" | "PATCH";
  responseSchema: z.ZodType<T>;
}

export function withBody<T>(
  endpoint: NotteEndpoint<T>,
  body: Record<string, unknown>,
): NotteEndpoint<T> & { body: Record<string, unknown> } {
  return { ...endpoint, body };
}

export function withParams<T>(
  endpoint: NotteEndpoint<T>,
  params: Record<string, unknown>,
): NotteEndpoint<T> & { params: Record<string, unknown> } {
  return { ...endpoint, params };
}
