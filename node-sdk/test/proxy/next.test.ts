import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createNotteProxy } from '@/proxy/next';
import { NotteProxyAuthError } from '@/proxy/types';

describe('createNotteProxy', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        headers: { 'content-type': 'application/json' },
      }),
    );
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('should return 401 if apiKey is not provided and env var is unset', async () => {
    const savedKey = process.env.NOTTE_API_KEY;
    delete process.env.NOTTE_API_KEY;
    try {
      const handlers = createNotteProxy({ authenticate: async () => {},});
      const request = new Request('http://localhost:3000/api/notte/sessions', {
        method: 'GET',
      });
      const response = await handlers.GET(request, { params: Promise.resolve({ path: ['sessions'] }) });
      expect(response.status).toBe(401);
      const body = await response.json();
      expect(body.error).toBe('No API key configured');
    } finally {
      if (savedKey !== undefined) process.env.NOTTE_API_KEY = savedKey;
    }
  });

  it('should return all 5 HTTP method handlers', () => {
    const handlers = createNotteProxy({ authenticate: async () => {}, apiKey: 'test-key' }); // pragma: allowlist secret

    expect(handlers.GET).toBeTypeOf('function');
    expect(handlers.POST).toBeTypeOf('function');
    expect(handlers.PUT).toBeTypeOf('function');
    expect(handlers.DELETE).toBeTypeOf('function');
    expect(handlers.PATCH).toBeTypeOf('function');
  });

  it('should handle GET requests correctly', async () => {
    const handlers = createNotteProxy({ authenticate: async () => {},
      apiKey: 'test-key', // pragma: allowlist secret
      apiUrl: 'https://mock-api.notte.cc',
    });

    const request = new Request('http://localhost:3000/api/notte/sessions', {
      method: 'GET',
    });
    const context = { params: Promise.resolve({ path: ['sessions'] }) };

    const response = await handlers.GET(request, context);
    expect(response.status).toBe(200);
  });

  it('should handle POST requests with body', async () => {
    const handlers = createNotteProxy({ authenticate: async () => {},
      apiKey: 'test-key', // pragma: allowlist secret
      apiUrl: 'https://mock-api.notte.cc',
    });

    const request = new Request('http://localhost:3000/api/notte/sessions/start', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ idle_timeout_minutes: 15 }),
    });
    const context = { params: Promise.resolve({ path: ['sessions', 'start'] }) };

    const response = await handlers.POST(request, context);
    expect(response.status).toBe(200);
  });

  it('should return 500 for unexpected errors in hooks', async () => {
    const handlers = createNotteProxy({ authenticate: async () => {},
      apiKey: 'test-key', // pragma: allowlist secret
      apiUrl: 'https://mock-api.notte.cc',
      onBeforeRequest: () => {
        throw new Error('Unexpected hook error');
      },
    });

    const request = new Request('http://localhost:3000/api/notte/sessions', {
      method: 'GET',
    });
    const context = { params: Promise.resolve({ path: ['sessions'] }) };

    const response = await handlers.GET(request, context);
    expect(response.status).toBe(500);
    const body = await response.json();
    expect(body.error).toBe('Unexpected hook error');
  });

  it('should return 502 when upstream fetch fails', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('Connection refused'));

    const handlers = createNotteProxy({ authenticate: async () => {},
      apiKey: 'test-key', // pragma: allowlist secret
      apiUrl: 'https://mock-api.notte.cc',
    });

    const request = new Request('http://localhost:3000/api/notte/sessions', {
      method: 'GET',
    });
    const context = { params: Promise.resolve({ path: ['sessions'] }) };

    const response = await handlers.GET(request, context);
    expect(response.status).toBe(502);
    const body = await response.json();
    expect(body.error).toBe('Failed to forward request to Notte API');
  });

  it('should return 401 for NotteProxyAuthError', async () => {
    const handlers = createNotteProxy({
      apiKey: 'test-key', // pragma: allowlist secret
      apiUrl: 'https://mock-api.notte.cc',
      authenticate: async () => {
        throw new NotteProxyAuthError('Access denied');
      },
    });

    const request = new Request('http://localhost:3000/api/notte/sessions', {
      method: 'GET',
    });
    const context = { params: Promise.resolve({ path: ['sessions'] }) };

    const response = await handlers.GET(request, context);
    expect(response.status).toBe(401);
    const body = await response.json();
    expect(body.error).toBe('Access denied');
  });

  it('should return 500 for non-auth errors from authenticate', async () => {
    const handlers = createNotteProxy({
      apiKey: 'test-key', // pragma: allowlist secret
      apiUrl: 'https://mock-api.notte.cc',
      authenticate: async () => {
        throw new Error('Database connection failed');
      },
    });

    const request = new Request('http://localhost:3000/api/notte/sessions', {
      method: 'GET',
    });
    const context = { params: Promise.resolve({ path: ['sessions'] }) };

    const response = await handlers.GET(request, context);
    expect(response.status).toBe(500);
    const body = await response.json();
    expect(body.error).toBe('Database connection failed');
  });

  it('should extract path segments from params promise', async () => {
    const handlers = createNotteProxy({ authenticate: async () => {},
      apiKey: 'test-key', // pragma: allowlist secret
      apiUrl: 'https://mock-api.notte.cc',
    });

    const request = new Request('http://localhost:3000/api/notte/agents/agent-123/stop', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: '{}',
    });
    const context = {
      params: Promise.resolve({ path: ['agents', 'agent-123', 'stop'] }),
    };

    const response = await handlers.POST(request, context);
    expect(response.status).toBe(200);

    const calledUrl = vi.mocked(globalThis.fetch).mock.calls[0]?.[0] as string;
    expect(calledUrl).toBe('https://mock-api.notte.cc/agents/agent-123/stop');
  });
});
