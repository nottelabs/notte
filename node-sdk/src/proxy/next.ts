import type { NotteProxyConfig } from './types';
import { handleProxyRequest } from './core';

/**
 * Type for a Next.js App Router route handler.
 * Uses standard Web API Request/Response (Next.js accepts these natively),
 * so `next` is NOT a dependency.
 */
type NextRouteHandler = (
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) => Promise<Response>;

/**
 * Creates Next.js App Router route handlers that proxy requests to the Notte API.
 *
 * This allows you to hide your Notte API key from client-side code by routing
 * requests through your own server.
 *
 * @example
 * ```typescript
 * // app/api/notte/[...path]/route.ts
 * import { createNotteProxy } from '@notte/sdk/next';
 *
 * export const { GET, POST, PUT, DELETE, PATCH } = createNotteProxy({
 *   apiKey: process.env.NOTTE_API_KEY!,
 * });
 * ```
 *
 * @example With authentication
 * ```typescript
 * import { createNotteProxy, NotteProxyAuthError } from '@notte/sdk/next';
 *
 * export const { GET, POST, PUT, DELETE, PATCH } = createNotteProxy({
 *   apiKey: process.env.NOTTE_API_KEY!,
 *   authenticate: async (request) => {
 *     const session = await getSession(request);
 *     if (!session) throw new NotteProxyAuthError('Not logged in');
 *   },
 * });
 * ```
 *
 * @example With per-user API keys
 * ```typescript
 * export const { GET, POST, PUT, DELETE, PATCH } = createNotteProxy({
 *   apiKey: 'fallback-key', // pragma: allowlist secret
 *   authenticate: async (request) => {
 *     const user = await getUser(request);
 *     if (!user) throw new NotteProxyAuthError();
 *     return user.notteApiKey; // returned string overrides apiKey
 *   },
 * });
 * ```
 */
export function createNotteProxy(config: NotteProxyConfig): {
  GET: NextRouteHandler;
  POST: NextRouteHandler;
  PUT: NextRouteHandler;
  DELETE: NextRouteHandler;
  PATCH: NextRouteHandler;
} {
  const resolvedConfig = { ...config };

  const makeHandler = (): NextRouteHandler => {
    return async (request, context) => {
      try {
        const { path } = await context.params;
        return await handleProxyRequest(request, path, resolvedConfig);
      } catch (error) {
        if (error instanceof Error) {
          return new Response(JSON.stringify({ error: error.message }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return new Response(
          JSON.stringify({ error: 'Internal server error' }),
          {
            status: 500,
            headers: { 'Content-Type': 'application/json' },
          },
        );
      }
    };
  };

  return {
    GET: makeHandler(),
    POST: makeHandler(),
    PUT: makeHandler(),
    DELETE: makeHandler(),
    PATCH: makeHandler(),
  };
}

// Re-export types and utilities for convenience
export type { NotteProxyConfig } from './types';
export { NotteProxyAuthError } from './types';
export { DEFAULT_ALLOWED_PATTERNS, validatePath } from './patterns';
export { handleProxyRequest } from './core';
