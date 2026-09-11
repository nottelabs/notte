import { describe, it, expect, beforeEach, vi } from 'vitest';
import { NotteClient } from '@/client';
import { createClient } from '@/lib/client/client';
const client = createClient();

/**
 * Tests for the redirect and Content-Type interceptors registered
 * by NotteClient on the hey-api client.
 *
 * We mock the generated client, construct a NotteClient (which registers
 * interceptors), then extract and call the response interceptor directly
 * to verify its behavior.
 */

vi.mock('@/lib/client/client', () => {
  const client = {
    setConfig: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
      error: { use: vi.fn() },
    },
  };
  return { createClient: () => client, createConfig: (config: unknown) => config };
});

function getResponseInterceptor() {
  // NotteClient registers the response interceptor via client.interceptors.response.use(fn)
  const calls = (client.interceptors.response.use as ReturnType<typeof vi.fn>).mock.calls;
  expect(calls.length).toBeGreaterThan(0);
  return calls[0][0] as (response: Response, request: Request, opts: any) => Promise<Response>;
}

describe('redirect & Content-Type response interceptor', () => {
  let interceptor: ReturnType<typeof getResponseInterceptor>;

  beforeEach(() => {
    vi.clearAllMocks();
    // Constructing NotteClient registers the interceptors
    new NotteClient({ apiKey: 'test-key' }); // pragma: allowlist secret
    interceptor = getResponseInterceptor();
  });

  describe('307 redirect handling', () => {
    it('should follow 307 redirect with original body', async () => {
      const lambdaResponse = new Response(JSON.stringify({ function_run_id: 'abc' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
      const mockGlobalFetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(lambdaResponse);

      const redirectResponse = new Response('', {
        status: 307,
        headers: { location: 'https://lambda.aws.com/function' },
      });
      const request = new Request('https://api.notte.cc/functions/abc/runs/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer sk-test' },
      });
      const opts = { serializedBody: '{"workflow_id":"test"}' };

      const result = await interceptor(redirectResponse, request, opts);

      expect(result.status).toBe(200);
      expect(mockGlobalFetch).toHaveBeenCalledTimes(1);

      // Check it was called with the redirect URL and preserved body
      const [url, init] = mockGlobalFetch.mock.calls[0];
      expect(url).toBe('https://lambda.aws.com/function');
      expect(init?.method).toBe('POST');
      expect(init?.body).toBe('{"workflow_id":"test"}');

      mockGlobalFetch.mockRestore();
    });

    it('should strip Authorization on cross-origin 307 redirect', async () => {
      const lambdaResponse = new Response('{}', {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
      const mockGlobalFetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(lambdaResponse);

      const redirectResponse = new Response('', {
        status: 307,
        headers: { location: 'https://lambda.aws.com/function' },
      });
      const request = new Request('https://api.notte.cc/endpoint', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer sk-secret' },
      });

      await interceptor(redirectResponse, request, { serializedBody: '{}' });

      const headers = new Headers(mockGlobalFetch.mock.calls[0][1]?.headers as Record<string, string>);
      expect(headers.has('Authorization')).toBe(false);

      mockGlobalFetch.mockRestore();
    });

    it('should preserve Authorization on same-origin 307 redirect', async () => {
      const response = new Response('{}', {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
      const mockGlobalFetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(response);

      const redirectResponse = new Response('', {
        status: 307,
        headers: { location: 'https://api.notte.cc/v2/endpoint' },
      });
      const request = new Request('https://api.notte.cc/endpoint', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer sk-secret' },
      });

      await interceptor(redirectResponse, request, { serializedBody: '{}' });

      const headers = new Headers(mockGlobalFetch.mock.calls[0][1]?.headers as Record<string, string>);
      expect(headers.get('Authorization')).toBe('Bearer sk-secret');

      mockGlobalFetch.mockRestore();
    });
  });

  describe('308 redirect handling', () => {
    it('should follow 308 redirect preserving method and body', async () => {
      const response = new Response('{"ok":true}', {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
      const mockGlobalFetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(response);

      const redirectResponse = new Response('', {
        status: 308,
        headers: { location: 'https://new.api.notte.cc/endpoint' },
      });
      const request = new Request('https://api.notte.cc/endpoint', {
        method: 'PUT',
      });

      await interceptor(redirectResponse, request, { serializedBody: '{"data":"value"}' });

      const [url, init] = mockGlobalFetch.mock.calls[0];
      expect(url).toBe('https://new.api.notte.cc/endpoint');
      expect(init?.method).toBe('PUT');
      expect(init?.body).toBe('{"data":"value"}');

      mockGlobalFetch.mockRestore();
    });
  });

  describe('Content-Type normalization', () => {
    it('should rewrite text/plain to application/json', async () => {
      const body = JSON.stringify({ function_run_id: 'abc123' });
      const response = new Response(body, {
        status: 200,
        headers: { 'content-type': 'text/plain; charset=utf-8' },
      });
      const request = new Request('https://lambda.aws.com/function');

      const result = await interceptor(response, request, {});

      expect(result.headers.get('content-type')).toBe('application/json');
      expect(await result.json()).toEqual({ function_run_id: 'abc123' });
    });

    it('should NOT touch application/json responses', async () => {
      const response = new Response('{"ok":true}', {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
      const request = new Request('https://api.notte.cc/endpoint');

      const result = await interceptor(response, request, {});

      // Should be the exact same response object, untouched
      expect(result).toBe(response);
    });

    it('should NOT touch text/html responses', async () => {
      const response = new Response('<html></html>', {
        status: 200,
        headers: { 'content-type': 'text/html' },
      });
      const request = new Request('https://api.notte.cc/endpoint');

      const result = await interceptor(response, request, {});
      expect(result).toBe(response);
    });
  });

  describe('non-redirect responses', () => {
    it('should pass through 200 application/json unchanged', async () => {
      const response = new Response('{"ok":true}', {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
      const request = new Request('https://api.notte.cc/endpoint');

      const result = await interceptor(response, request, {});
      expect(result).toBe(response);
    });

    it('should pass through 4xx/5xx unchanged', async () => {
      const response = new Response('Not Found', {
        status: 404,
        headers: { 'content-type': 'application/json' },
      });
      const request = new Request('https://api.notte.cc/missing');

      const result = await interceptor(response, request, {});
      expect(result).toBe(response);
    });
  });
});

describe('redirect credential hardening', () => {
  let interceptor: ReturnType<typeof getResponseInterceptor>;

  beforeEach(() => {
    vi.clearAllMocks();
    new NotteClient({ apiKey: 'test-key' }); // pragma: allowlist secret
    interceptor = getResponseInterceptor();
  });

  it('strips x-notte-api-key as well as Authorization on cross-origin redirects', async () => {
    const mockGlobalFetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('{}', { status: 200 }));
    const redirectResponse = new Response('', { status: 307, headers: { location: 'https://lambda.aws.com/function' } });
    const request = new Request('https://api.notte.cc/functions/x/runs/y', {
      method: 'POST',
      headers: { Authorization: 'Bearer sk-secret', 'x-notte-api-key': 'sk-secret' }, // pragma: allowlist secret
    });

    await interceptor(redirectResponse, request, { serializedBody: '{}' });

    const headers = new Headers(mockGlobalFetch.mock.calls[0][1]?.headers as Record<string, string>);
    expect(headers.has('Authorization')).toBe(false);
    expect(headers.has('x-notte-api-key')).toBe(false);
    mockGlobalFetch.mockRestore();
  });

  it('keeps x-notte-api-key on same-origin redirects', async () => {
    const mockGlobalFetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('{}', { status: 200 }));
    const redirectResponse = new Response('', { status: 308, headers: { location: 'https://api.notte.cc/v2/functions' } });
    const request = new Request('https://api.notte.cc/functions', {
      method: 'POST',
      headers: { 'x-notte-api-key': 'sk-secret' }, // pragma: allowlist secret
    });

    await interceptor(redirectResponse, request, { serializedBody: '{}' });

    const headers = new Headers(mockGlobalFetch.mock.calls[0][1]?.headers as Record<string, string>);
    expect(headers.get('x-notte-api-key')).toBe('sk-secret'); // pragma: allowlist secret
    mockGlobalFetch.mockRestore();
  });

  it('refuses to follow redirects to plaintext http destinations', async () => {
    const mockGlobalFetch = vi.spyOn(globalThis, 'fetch');
    const redirectResponse = new Response('', { status: 307, headers: { location: 'http://insecure.example/function' } });
    const request = new Request('https://api.notte.cc/endpoint', { method: 'POST', headers: { Authorization: 'Bearer sk-secret' } }); // pragma: allowlist secret

    await expect(interceptor(redirectResponse, request, { serializedBody: '{}' })).rejects.toThrow('insecure URL');
    expect(mockGlobalFetch).not.toHaveBeenCalled();
    mockGlobalFetch.mockRestore();
  });

  it('allows http redirects to loopback for local development', async () => {
    const mockGlobalFetch = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('{}', { status: 200 }));
    const redirectResponse = new Response('', { status: 307, headers: { location: 'http://localhost:8000/function' } });
    const request = new Request('https://api.notte.cc/endpoint', { method: 'POST' });

    await interceptor(redirectResponse, request, { serializedBody: '{}' });

    expect(mockGlobalFetch).toHaveBeenCalledTimes(1);
    mockGlobalFetch.mockRestore();
  });
});
