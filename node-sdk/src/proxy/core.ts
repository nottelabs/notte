import { validatePath, DEFAULT_ALLOWED_PATTERNS } from './patterns';
import type { NotteProxyConfig } from './types';
import { NotteProxyAuthError } from './types';

const DEFAULT_API_URL = 'https://api.notte.cc';
const DEFAULT_FORWARD_HEADERS = ['content-type', 'accept'];
const METHODS_WITH_BODY = ['POST', 'PUT', 'PATCH'];

/**
 * Framework-agnostic proxy handler that forwards requests to the Notte API.
 *
 * Takes a standard Web API `Request`, injects authentication, and returns
 * a standard Web API `Response`. Works with any runtime that supports
 * the Web API standards (Node 18+, Deno, Bun, Cloudflare Workers).
 *
 * @param request - The incoming HTTP request (standard Web API Request)
 * @param pathSegments - The path segments after the proxy base path (e.g., ['sessions', 'start'])
 * @param config - Proxy configuration including API key, auth hooks, etc.
 * @returns A standard Web API Response
 */
export async function handleProxyRequest(
  request: Request,
  pathSegments: string[],
  config: NotteProxyConfig,
): Promise<Response> {
  try {
    // Step 1: Path validation
    if (config.allowedPatterns !== false) {
      const patterns = config.allowedPatterns || DEFAULT_ALLOWED_PATTERNS;
      const pathValidation = validatePath(pathSegments, patterns);

      if (!pathValidation.isValid) {
        return new Response(
          JSON.stringify({
            error: 'Invalid API endpoint',
            details: pathValidation.error,
          }),
          {
            status: 400,
            headers: { 'Content-Type': 'application/json' },
          },
        );
      }
    }

    // Step 2: Authentication
    if (typeof config.authenticate !== 'function') {
      throw new NotteProxyAuthError('Proxy caller authentication is required');
    }
    let apiKey = config.apiKey || process.env.NOTTE_API_KEY;

    if (config.authenticate) {
      const result = await config.authenticate(request);
      if (typeof result === 'string') {
        apiKey = result;
      }
    }

    if (!apiKey) {
      return new Response(
        JSON.stringify({ error: 'No API key configured' }),
        {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        },
      );
    }

    // Step 3: Build target URL
    const apiUrl = (config.apiUrl || DEFAULT_API_URL).replace(/\/$/, '');
    const path = pathSegments.join('/');
    const incomingUrl = new URL(request.url);
    const searchParams = incomingUrl.searchParams.toString();
    const targetUrl = `${apiUrl}/${path}${searchParams ? `?${searchParams}` : ''}`;

    // Step 4: Build headers
    const forwardHeaders = new Headers();
    forwardHeaders.set('Authorization', `Bearer ${apiKey}`);
    // Function run endpoints authenticate with their own header (the API does
    // not forward `Authorization` to the runtime), so inject it as well.
    forwardHeaders.set('x-notte-api-key', apiKey);
    forwardHeaders.set(
      'x-notte-request-origin',
      config.requestOrigin || 'sdk-proxy',
    );

    const headersToForward =
      config.forwardHeaders || DEFAULT_FORWARD_HEADERS;
    for (const header of headersToForward) {
      const value = request.headers.get(header);
      if (value) {
        forwardHeaders.set(header, value);
      }
    }

    // Step 5: onBeforeRequest hook
    if (config.onBeforeRequest) {
      await config.onBeforeRequest({
        path,
        method: request.method,
        headers: forwardHeaders,
        url: targetUrl,
        incomingRequest: request,
      });
    }

    // Step 6: Forward the request
    const requestOptions: RequestInit = {
      method: request.method,
      headers: forwardHeaders,
      signal: request.signal,
    };

    if (METHODS_WITH_BODY.includes(request.method) && request.body) {
      requestOptions.body = request.body;
      (requestOptions as any).duplex = 'half';
    }

    let response: globalThis.Response;
    try {
      response = await fetch(targetUrl, requestOptions);
    } catch (fetchError) {
      const errorMessage =
        fetchError instanceof Error
          ? fetchError.message
          : 'Unknown fetch error';
      return new Response(
        JSON.stringify({
          error: 'Failed to forward request to Notte API',
          details: errorMessage,
        }),
        {
          status: 502,
          headers: { 'Content-Type': 'application/json' },
        },
      );
    }

    // Step 7: Handle response
    const contentType = response.headers.get('content-type') || '';

    const isBinaryResponse =
      contentType.startsWith('image/') ||
      contentType.startsWith('video/') ||
      contentType.startsWith('audio/') ||
      contentType.includes('octet-stream');

    const isStreamingResponse = contentType.includes('text/event-stream');

    // For streaming responses, pass through the body with appropriate headers
    if (isStreamingResponse && response.body) {
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: {
          'Content-Type': contentType,
          'Cache-Control': 'no-cache',
          Connection: 'keep-alive',
        },
      });
    }

    // For all other responses with a body stream, pass it through directly
    if (response.body) {
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: {
          'Content-Type': contentType,
        },
      });
    }

    // Fallback for responses without a body stream: buffer appropriately
    if (isBinaryResponse) {
      const data = await response.arrayBuffer();
      return new Response(data, {
        status: response.status,
        statusText: response.statusText,
        headers: { 'Content-Type': contentType },
      });
    }

    // Fallback: buffer as text
    const data = await response.text();
    return new Response(data, {
      status: response.status,
      statusText: response.statusText,
      headers: { 'Content-Type': contentType },
    });
  } catch (error) {
    // NotteProxyAuthError from authenticate() → 401
    if (error instanceof NotteProxyAuthError) {
      return new Response(
        JSON.stringify({ error: error.message }),
        {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        },
      );
    }

    // Re-throw unexpected errors so the adapter layer can handle them
    throw error;
  }
}
