import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { handleProxyRequest } from '@/proxy/core';
import type { NotteProxyConfig } from '@/proxy/types';
import { NotteProxyAuthError } from '@/proxy/types';
import { NotteClient } from '@/client';
import { FunctionRunRejectedError } from '@/errors';

// Helper to create a Request object
function makeRequest(
  path: string,
  options: {
    method?: string;
    body?: string;
    headers?: Record<string, string>;
  } = {},
): Request {
  const { method = 'GET', body, headers = {} } = options;
  return new Request(`http://localhost:3000/api/notte/${path}`, {
    method,
    body: method !== 'GET' && method !== 'DELETE' ? body : undefined,
    headers: {
      'content-type': 'application/json',
      ...headers,
    },
  });
}

function baseConfig(overrides: Partial<NotteProxyConfig> = {}): NotteProxyConfig {
  return {
    authenticate: async () => {},
    apiKey: 'test-api-key', // pragma: allowlist secret
    apiUrl: 'https://mock-api.notte.cc',
    ...overrides,
  };
}

describe('handleProxyRequest', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    // Mock global fetch
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('rejects requests without caller authentication even with a server key', async () => {
    const response = await handleProxyRequest(makeRequest('sessions'), ['sessions'], baseConfig({ authenticate: undefined }));
    expect(response.status).toBe(401);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  describe('path validation', () => {
    it('should return 400 for invalid paths', async () => {
      const request = makeRequest('unknown/endpoint');
      const response = await handleProxyRequest(request, ['unknown', 'endpoint'], baseConfig());

      expect(response.status).toBe(400);
      const body = await response.json();
      expect(body.error).toBe('Invalid API endpoint');
    });

    it('should allow valid paths', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const request = makeRequest('sessions/start');
      const response = await handleProxyRequest(request, ['sessions', 'start'], baseConfig());

      expect(response.status).toBe(200);
    });

    it('should skip validation when allowedPatterns is false', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const request = makeRequest('any/custom/path');
      const response = await handleProxyRequest(
        request,
        ['any', 'custom', 'path'],
        baseConfig({ allowedPatterns: false }),
      );

      expect(response.status).toBe(200);
    });

    it('should use custom allowedPatterns when provided', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const customPatterns = [/^custom\/route$/];
      const request = makeRequest('custom/route');
      const response = await handleProxyRequest(
        request,
        ['custom', 'route'],
        baseConfig({ allowedPatterns: customPatterns }),
      );

      expect(response.status).toBe(200);
    });
  });

  describe('authentication', () => {
    it('should use the default apiKey', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const request = makeRequest('sessions');
      await handleProxyRequest(request, ['sessions'], baseConfig());

      expect(globalThis.fetch).toHaveBeenCalledWith(
        'https://mock-api.notte.cc/sessions',
        expect.objectContaining({
          headers: expect.any(Headers),
        }),
      );

      const calledHeaders = vi.mocked(globalThis.fetch).mock.calls[0]?.[1]?.headers as Headers;
      expect(calledHeaders.get('Authorization')).toBe('Bearer test-api-key');
    });

    it('should override apiKey when authenticate returns a string', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const request = makeRequest('sessions');
      await handleProxyRequest(
        request,
        ['sessions'],
        baseConfig({
          authenticate: async () => 'user-specific-key',
        }),
      );

      const calledHeaders = vi.mocked(globalThis.fetch).mock.calls[0]?.[1]?.headers as Headers;
      expect(calledHeaders.get('Authorization')).toBe('Bearer user-specific-key');
      expect(calledHeaders.get('x-notte-api-key')).toBe('user-specific-key');
    });

    it('should use default apiKey when authenticate returns void', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const request = makeRequest('sessions');
      await handleProxyRequest(
        request,
        ['sessions'],
        baseConfig({
          authenticate: async () => {
            // validation passes, return void
          },
        }),
      );

      const calledHeaders = vi.mocked(globalThis.fetch).mock.calls[0]?.[1]?.headers as Headers;
      expect(calledHeaders.get('Authorization')).toBe('Bearer test-api-key');
    });

    it('should return 401 when authenticate throws NotteProxyAuthError', async () => {
      const request = makeRequest('sessions');
      const response = await handleProxyRequest(
        request,
        ['sessions'],
        baseConfig({
          authenticate: async () => {
            throw new NotteProxyAuthError('Access denied');
          },
        }),
      );

      expect(response.status).toBe(401);
      const body = await response.json();
      expect(body.error).toBe('Access denied');
    });

    it('should re-throw non-auth errors from authenticate', async () => {
      const request = makeRequest('sessions');
      await expect(
        handleProxyRequest(
          request,
          ['sessions'],
          baseConfig({
            authenticate: async () => {
              throw new Error('Some unexpected error');
            },
          }),
        ),
      ).rejects.toThrow('Some unexpected error');
    });
  });

  describe('request forwarding', () => {
    it('should build the correct target URL', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const request = makeRequest('sessions/start');
      await handleProxyRequest(request, ['sessions', 'start'], baseConfig());

      expect(globalThis.fetch).toHaveBeenCalledWith(
        'https://mock-api.notte.cc/sessions/start',
        expect.anything(),
      );
    });

    it('should forward query parameters', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const request = new Request('http://localhost:3000/api/notte/sessions?limit=10&offset=0', {
        method: 'GET',
        headers: { 'content-type': 'application/json' },
      });
      await handleProxyRequest(request, ['sessions'], baseConfig());

      const calledUrl = vi.mocked(globalThis.fetch).mock.calls[0]?.[0] as string;
      expect(calledUrl).toBe('https://mock-api.notte.cc/sessions?limit=10&offset=0');
    });

    it('should forward body for POST requests', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ session_id: '123' }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const bodyPayload = JSON.stringify({ idle_timeout_minutes: 15 });
      const request = makeRequest('sessions/start', {
        method: 'POST',
        body: bodyPayload,
      });
      await handleProxyRequest(request, ['sessions', 'start'], baseConfig());

      const calledOptions = vi.mocked(globalThis.fetch).mock.calls[0]?.[1] as RequestInit;
      expect(calledOptions.method).toBe('POST');
      expect(calledOptions.body).toBeInstanceOf(ReadableStream);
    });

    it('should forward body for PUT requests', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const bodyPayload = JSON.stringify({ name: 'updated' });
      const request = makeRequest('workflows/wf-123', {
        method: 'PUT',
        body: bodyPayload,
      });
      await handleProxyRequest(
        request,
        ['workflows', 'wf-123'],
        baseConfig({ allowedPatterns: false }),
      );

      const calledOptions = vi.mocked(globalThis.fetch).mock.calls[0]?.[1] as RequestInit;
      expect(calledOptions.method).toBe('PUT');
      expect(calledOptions.body).toBeInstanceOf(ReadableStream);
    });

    it('should NOT forward body for GET requests', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const request = makeRequest('sessions');
      await handleProxyRequest(request, ['sessions'], baseConfig());

      const calledOptions = vi.mocked(globalThis.fetch).mock.calls[0]?.[1] as RequestInit;
      expect(calledOptions.body).toBeUndefined();
    });

    it('should NOT forward body for DELETE requests', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const request = makeRequest('sessions/abc-123/stop', { method: 'DELETE' });
      await handleProxyRequest(request, ['sessions', 'abc-123', 'stop'], baseConfig());

      const calledOptions = vi.mocked(globalThis.fetch).mock.calls[0]?.[1] as RequestInit;
      expect(calledOptions.body).toBeUndefined();
    });
  });

  describe('headers', () => {
    it('should set x-notte-request-origin header', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const request = makeRequest('sessions');
      await handleProxyRequest(request, ['sessions'], baseConfig());

      const calledHeaders = vi.mocked(globalThis.fetch).mock.calls[0]?.[1]?.headers as Headers;
      expect(calledHeaders.get('x-notte-request-origin')).toBe('sdk-proxy');
    });

    it('should use custom requestOrigin', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const request = makeRequest('sessions');
      await handleProxyRequest(
        request,
        ['sessions'],
        baseConfig({ requestOrigin: 'my-app' }),
      );

      const calledHeaders = vi.mocked(globalThis.fetch).mock.calls[0]?.[1]?.headers as Headers;
      expect(calledHeaders.get('x-notte-request-origin')).toBe('my-app');
    });

    it('should forward default headers (content-type, accept)', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const request = new Request('http://localhost:3000/api/notte/sessions', {
        headers: {
          'content-type': 'application/json',
          accept: 'application/json',
        },
      });
      await handleProxyRequest(request, ['sessions'], baseConfig());

      const calledHeaders = vi.mocked(globalThis.fetch).mock.calls[0]?.[1]?.headers as Headers;
      expect(calledHeaders.get('content-type')).toBe('application/json');
      expect(calledHeaders.get('accept')).toBe('application/json');
    });

    it('should forward custom headers when specified', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const request = new Request('http://localhost:3000/api/notte/sessions', {
        headers: {
          'content-type': 'application/json',
          'x-custom-header': 'custom-value',
        },
      });
      await handleProxyRequest(
        request,
        ['sessions'],
        baseConfig({ forwardHeaders: ['content-type', 'x-custom-header'] }),
      );

      const calledHeaders = vi.mocked(globalThis.fetch).mock.calls[0]?.[1]?.headers as Headers;
      expect(calledHeaders.get('x-custom-header')).toBe('custom-value');
    });
  });

  describe('the rejected run status opt-in', () => {
    // NotteClient asks for the `rejected` status on functions requests. Dropping
    // the header here would make runs through the proxy report deliberate
    // refusals as `failed`.
    const OPT_IN = 'x-notte-accept-run-statuses';
    const upstreamHeaders = () => vi.mocked(globalThis.fetch).mock.calls[0]?.[1]?.headers as Headers;
    const runRequest = (headers: Record<string, string>) =>
      new Request('http://localhost:3000/api/notte/functions/fn-1/runs/run-1', { method: 'POST', body: '{}', headers });

    beforeEach(() => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), { headers: { 'content-type': 'application/json' } }),
      );
    });

    it('forwards it by default', async () => {
      await handleProxyRequest(runRequest({ [OPT_IN]: 'rejected' }), ['functions', 'fn-1', 'runs', 'run-1'], baseConfig());

      expect(upstreamHeaders().get(OPT_IN)).toBe('rejected');
    });

    it('forwards it alongside a caller-configured list, which keeps working', async () => {
      await handleProxyRequest(
        runRequest({ [OPT_IN]: 'rejected', 'x-custom-header': 'custom-value' }),
        ['functions', 'fn-1', 'runs', 'run-1'],
        baseConfig({ forwardHeaders: ['content-type', 'x-custom-header'] }),
      );

      expect(upstreamHeaders().get(OPT_IN)).toBe('rejected');
      expect(upstreamHeaders().get('x-custom-header')).toBe('custom-value');
      expect(upstreamHeaders().get('accept')).toBeNull();
    });

    it('does not add it to a request that did not ask', async () => {
      await handleProxyRequest(runRequest({}), ['functions', 'fn-1', 'runs', 'run-1'], baseConfig());

      expect(upstreamHeaders().has(OPT_IN)).toBe(false);
    });

    it('lets a client behind the proxy receive a rejected run as FunctionRunRejectedError', async () => {
      const error = {
        kind: 'expected', type: 'AccountNotUnique', mro: ['AccountNotUnique', 'ValueError', 'ExpectedFunctionError'],
        code: 'account_not_unique', message: '2 accounts match this phone number',
        heal: false, retry: false, status_code: 409, source: 'class',
      };
      const upstream: Request[] = [];
      // One fetch serves both hops: the client calls the app's proxy route,
      // and the proxy calls the API, which answers `rejected` only when asked.
      vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
        const request = new Request(input, init);
        const url = new URL(request.url);
        if (url.host === 'app.example.com') {
          const segments = url.pathname.replace(/^\/api\/notte\//, '').split('/');
          return handleProxyRequest(request, segments, baseConfig());
        }
        upstream.push(request);
        if (url.pathname.endsWith('/runs/create')) {
          return Response.json({ function_id: 'fn-1', function_run_id: 'run-1', created_at: '2026-01-01T00:00:00Z', status: 'created' });
        }
        const rejected = request.headers.get(OPT_IN) === 'rejected';
        return Response.json({
          function_id: 'fn-1', function_run_id: 'run-1', session_id: null,
          status: rejected ? 'rejected' : 'failed',
          result: 'AccountNotUnique: 2 accounts match this phone number', error,
        });
      });
      vi.spyOn(console, 'warn').mockImplementation(() => {});
      const client = new NotteClient({ apiKey: 'client-key', baseUrl: 'https://app.example.com/api/notte' }); // pragma: allowlist secret

      const run = client.NotteFunction({ function_id: 'fn-1' }).run({}, { stream: false });

      await expect(run).rejects.toBeInstanceOf(FunctionRunRejectedError);
      await expect(run).rejects.toMatchObject({ code: 'account_not_unique', error });
      expect(upstream.map(request => request.headers.get(OPT_IN))).toEqual(['rejected', 'rejected']);
    });
  });

  describe('onBeforeRequest hook', () => {
    it('should call onBeforeRequest with correct context', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const onBeforeRequest = vi.fn();
      const request = makeRequest('sessions/start');
      await handleProxyRequest(
        request,
        ['sessions', 'start'],
        baseConfig({ onBeforeRequest }),
      );

      expect(onBeforeRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          path: 'sessions/start',
          method: 'GET',
          url: 'https://mock-api.notte.cc/sessions/start',
          headers: expect.any(Headers),
          incomingRequest: request,
        }),
      );
    });

    it('should allow onBeforeRequest to modify headers', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const request = makeRequest('sessions');
      await handleProxyRequest(
        request,
        ['sessions'],
        baseConfig({
          onBeforeRequest: ({ headers }) => {
            headers.set('x-custom', 'injected-value');
          },
        }),
      );

      const calledHeaders = vi.mocked(globalThis.fetch).mock.calls[0]?.[1]?.headers as Headers;
      expect(calledHeaders.get('x-custom')).toBe('injected-value');
    });
  });

  describe('response handling', () => {
    it('should forward JSON responses', async () => {
      const responseBody = { session_id: '123', status: 'active' };
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify(responseBody), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      );

      const request = makeRequest('sessions/start');
      const response = await handleProxyRequest(request, ['sessions', 'start'], baseConfig());

      expect(response.status).toBe(200);
      expect(response.headers.get('content-type')).toBe('application/json');
      const body = await response.json();
      expect(body).toEqual(responseBody);
    });

    it('should forward error status codes from upstream', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ error: 'Not found' }), {
          status: 404,
          headers: { 'content-type': 'application/json' },
        }),
      );

      const request = makeRequest('sessions/nonexistent');
      const response = await handleProxyRequest(
        request,
        ['sessions', 'nonexistent'],
        baseConfig({ allowedPatterns: false }),
      );

      expect(response.status).toBe(404);
    });

    it('should handle streaming SSE responses', async () => {
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(new TextEncoder().encode('data: {"step": 1}\n\n'));
          controller.close();
        },
      });

      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(stream, {
          status: 200,
          headers: { 'content-type': 'text/event-stream' },
        }),
      );

      const request = makeRequest('anything/start', { method: 'POST', body: '{}' });
      const response = await handleProxyRequest(request, ['anything', 'start'], baseConfig());

      expect(response.status).toBe(200);
      expect(response.headers.get('content-type')).toBe('text/event-stream');
      expect(response.headers.get('cache-control')).toBe('no-cache');
      expect(response.body).toBeTruthy();
    });

    it('should handle binary responses', async () => {
      const binaryData = new Uint8Array([137, 80, 78, 71]); // PNG header
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(null, {
          status: 200,
          headers: { 'content-type': 'image/png' },
        }),
      );

      // Mock arrayBuffer method since Response with null body
      const mockResponse = new Response(binaryData, {
        status: 200,
        headers: { 'content-type': 'image/png' },
      });
      // Override body to null to trigger binary path
      Object.defineProperty(mockResponse, 'body', { value: null });
      vi.mocked(globalThis.fetch).mockResolvedValue(mockResponse);

      const request = makeRequest('storage/sess-123/downloads/screenshot.png');
      const response = await handleProxyRequest(
        request,
        ['storage', 'sess-123', 'downloads', 'screenshot.png'],
        baseConfig({ allowedPatterns: false }),
      );

      expect(response.status).toBe(200);
      expect(response.headers.get('content-type')).toBe('image/png');
    });

    it('should return 502 when fetch fails', async () => {
      vi.mocked(globalThis.fetch).mockRejectedValue(new Error('Connection refused'));

      const request = makeRequest('sessions');
      const response = await handleProxyRequest(request, ['sessions'], baseConfig());

      expect(response.status).toBe(502);
      const body = await response.json();
      expect(body.error).toBe('Failed to forward request to Notte API');
      expect(body.details).toBe('Connection refused');
    });
  });

  describe('apiUrl configuration', () => {
    it('should use default API URL when not configured', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const request = makeRequest('sessions');
      await handleProxyRequest(request, ['sessions'], baseConfig({ apiUrl: undefined }));

      const calledUrl = vi.mocked(globalThis.fetch).mock.calls[0]?.[0] as string;
      expect(calledUrl).toBe('https://api.notte.cc/sessions');
    });

    it('should strip trailing slash from apiUrl', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          headers: { 'content-type': 'application/json' },
        }),
      );

      const request = makeRequest('sessions');
      await handleProxyRequest(
        request,
        ['sessions'],
        baseConfig({ apiUrl: 'https://custom.api.com/' }),
      );

      const calledUrl = vi.mocked(globalThis.fetch).mock.calls[0]?.[0] as string;
      expect(calledUrl).toBe('https://custom.api.com/sessions');
    });
  });
});
