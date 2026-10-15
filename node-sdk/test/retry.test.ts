import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { once } from 'node:events';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { NotteClient } from '@/client';
import { InvalidRequestError, NotteAPIError } from '@/errors';
import {
  backoffDelayMs,
  createRetryingFetch,
  DEFAULT_MAX_RETRIES,
  parseRetryAfter,
  RETRY_AFTER_MAX_MS,
  RETRY_BASE_DELAY_MS,
  RETRY_MAX_DELAY_MS,
  retryDelayMs,
} from '@/retry';

const networkError = (code: string) => new TypeError('fetch failed', { cause: Object.assign(new Error(code), { code }) });

describe('retry policy helpers', () => {
  it('bounds exponential backoff with full jitter', () => {
    expect(backoffDelayMs(0, () => 1)).toBe(RETRY_BASE_DELAY_MS);
    expect(backoffDelayMs(1, () => 1)).toBe(RETRY_BASE_DELAY_MS * 2);
    expect(backoffDelayMs(2, () => 0.5)).toBe(RETRY_BASE_DELAY_MS * 2);
    for (let attempt = 0; attempt < 50; attempt++) {
      expect(backoffDelayMs(attempt, () => 1)).toBeLessThanOrEqual(RETRY_MAX_DELAY_MS);
      expect(backoffDelayMs(attempt, () => 0)).toBe(0);
    }
    // Worst case with defaults stays well under a minute.
    let total = 0;
    for (let attempt = 0; attempt < DEFAULT_MAX_RETRIES; attempt++) {
      total += Math.max(backoffDelayMs(attempt, () => 1), RETRY_AFTER_MAX_MS);
    }
    expect(total).toBeLessThanOrEqual(60_000);
  });

  it('parses Retry-After seconds and HTTP dates', () => {
    expect(parseRetryAfter('3')).toBe(3000);
    expect(parseRetryAfter('0.5')).toBe(500);
    expect(parseRetryAfter(new Date(10_000).toUTCString(), 4_000)).toBe(6000);
    expect(parseRetryAfter(new Date(1_000).toUTCString(), 4_000)).toBe(0);
    expect(parseRetryAfter('soon')).toBeUndefined();
    expect(parseRetryAfter(null)).toBeUndefined();
  });

  it('prefers Retry-After over backoff and refuses waits above the cap', () => {
    expect(retryDelayMs(0, '2', () => 1)).toBe(2000);
    expect(retryDelayMs(0, null, () => 1)).toBe(RETRY_BASE_DELAY_MS);
    expect(retryDelayMs(0, String(RETRY_AFTER_MAX_MS / 1000 + 1))).toBeUndefined();
  });
});

describe('createRetryingFetch', () => {
  const sleep = vi.fn(async () => {});
  const make = (fetchImpl: typeof fetch, maxRetries = 3, deadline?: number) =>
    createRetryingFetch({ maxRetries: () => maxRetries, fetch: fetchImpl, sleep, random: () => 1, deadline: () => deadline });
  const respond = (status: number, headers: Record<string, string> = {}) => new Response(String(status), { status, headers });

  beforeEach(() => {
    sleep.mockClear();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });
  afterEach(() => vi.restoreAllMocks());

  it('honors Retry-After', async () => {
    const fetchImpl = vi.fn().mockResolvedValueOnce(respond(529, { 'retry-after': '7' })).mockResolvedValueOnce(respond(200));
    const response = await make(fetchImpl)('https://api.test/sessions/start', { method: 'POST', body: '{}' });
    expect(response.status).toBe(200);
    expect(sleep).toHaveBeenCalledExactlyOnceWith(7000, undefined);
  });

  it('returns the response when Retry-After exceeds the cap', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(respond(503, { 'retry-after': '120' }));
    const response = await make(fetchImpl)('https://api.test/x');
    expect(response.status).toBe(503);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('backs off exponentially between attempts', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(respond(503));
    const response = await make(fetchImpl)('https://api.test/x');
    expect(response.status).toBe(503);
    expect(fetchImpl).toHaveBeenCalledTimes(4);
    expect(sleep.mock.calls.map(call => (call as unknown[])[0])).toEqual([1000, 2000, 4000]);
  });

  it('does not wait past the request deadline', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(respond(503, { 'retry-after': '5' }));
    const response = await make(fetchImpl, 3, Date.now() + 1000)('https://api.test/x');
    expect(response.status).toBe(503);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(sleep).not.toHaveBeenCalled();
  });

  it('retries connection failures that happen before the request is sent, for any method', async () => {
    const fetchImpl = vi.fn()
      .mockRejectedValueOnce(networkError('ECONNREFUSED'))
      .mockRejectedValueOnce(new TypeError('fetch failed', { cause: new AggregateError([networkError('UND_ERR_CONNECT_TIMEOUT').cause]) }))
      .mockResolvedValueOnce(respond(200));
    const response = await make(fetchImpl)('https://api.test/agents/start', { method: 'POST', body: '{}' });
    expect(response.status).toBe(200);
    expect(fetchImpl).toHaveBeenCalledTimes(3);
  });

  it('retries connection resets only for idempotent methods', async () => {
    const reset = () => vi.fn().mockRejectedValueOnce(networkError('ECONNRESET')).mockResolvedValueOnce(respond(200));
    const get = reset();
    expect((await make(get)('https://api.test/x', { method: 'GET' })).status).toBe(200);
    expect(get).toHaveBeenCalledTimes(2);

    const post = reset();
    await expect(make(post)('https://api.test/x', { method: 'POST', body: '{}' })).rejects.toThrow('fetch failed');
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('never retries non-network errors', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError'));
    await expect(make(fetchImpl)('https://api.test/x')).rejects.toThrow('aborted');
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('replays a Request body on every attempt', async () => {
    const bodies: string[] = [];
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      bodies.push(await (input as Request).text());
      return respond(bodies.length < 3 ? 503 : 200);
    });
    const request = new Request('https://api.test/x', { method: 'POST', body: '{"a":1}' });
    expect((await make(fetchImpl as typeof fetch)(request)).status).toBe(200);
    expect(bodies).toEqual(['{"a":1}', '{"a":1}', '{"a":1}']);
  });
});

describe('NotteClient retries', () => {
  let apiUrl: string;
  let handler: (req: IncomingMessage, res: ServerResponse) => void;
  let hits = 0;
  const server = createServer((req, res) => {
    hits++;
    handler(req, res);
  });
  const json = (res: ServerResponse, status: number, body: unknown = {}) => {
    res.writeHead(status, { 'content-type': 'application/json' });
    res.end(JSON.stringify(body));
  };
  /** Answer `status` until the last attempt, then 200. */
  const failThenSucceed = (status: number, failures: number) => {
    handler = (_req, res) => (hits <= failures ? json(res, status, { message: 'transient' }) : json(res, 200, { status: 'ok' }));
  };
  const client = (maxRetries?: number) =>
    new NotteClient({ baseUrl: apiUrl, apiKey: 'test-key', timeoutMs: 5000, maxRetries }); // pragma: allowlist secret
  const search = (c: NotteClient) => c.search('notte');

  beforeAll(async () => {
    vi.stubEnv('NOTTE_SDK_DISABLE_VERSION_CHECK', '1');
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    apiUrl = `http://127.0.0.1:${(server.address() as { port: number }).port}`;
  });
  afterAll(async () => {
    vi.unstubAllEnvs();
    server.closeAllConnections();
    await new Promise<void>(resolve => server.close(() => resolve()));
  });
  beforeEach(() => {
    hits = 0;
    vi.spyOn(Math, 'random').mockReturnValue(0);
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });
  afterEach(() => vi.restoreAllMocks());

  it.each([502, 503, 504, 529])('retries GET requests on %i', async status => {
    failThenSucceed(status, 2);
    await client().healthCheck();
    expect(hits).toBe(3);
  });

  it.each([503, 529])('retries POST requests on %i', async status => {
    failThenSucceed(status, 1);
    await search(client());
    expect(hits).toBe(2);
  });

  it.each([502, 504])('does not retry POST requests on %i, which may have been processed', async status => {
    failThenSucceed(status, 1);
    await expect(search(client())).rejects.toMatchObject({ statusCode: status });
    expect(hits).toBe(1);
  });

  it.each([500, 400, 401, 404, 409, 422, 429])('never retries %i', async status => {
    failThenSucceed(status, 10);
    await expect(client().healthCheck()).rejects.toBeInstanceOf(NotteAPIError);
    expect(hits).toBe(1);
    hits = 0;
    await expect(search(client())).rejects.toMatchObject({ statusCode: status });
    expect(hits).toBe(1);
  });

  it('gives up after maxRetries and surfaces the last error', async () => {
    failThenSucceed(503, 10);
    await expect(client(2).healthCheck()).rejects.toMatchObject({ statusCode: 503 });
    expect(hits).toBe(3);
  });

  it('honors Retry-After from the API', async () => {
    handler = (_req, res) => {
      if (hits === 1) {
        res.writeHead(529, { 'content-type': 'application/json', 'retry-after': '0.2' });
        res.end('{}');
      } else json(res, 200);
    };
    const started = Date.now();
    await client().healthCheck();
    expect(hits).toBe(2);
    expect(Date.now() - started).toBeGreaterThanOrEqual(190);
  });

  it('can be disabled with maxRetries: 0', async () => {
    failThenSucceed(503, 10);
    await expect(client(0).healthCheck()).rejects.toMatchObject({ statusCode: 503 });
    expect(hits).toBe(1);
  });

  it('retries a refused connection', async () => {
    const closed = createServer();
    closed.listen(0, '127.0.0.1');
    await once(closed, 'listening');
    const port = (closed.address() as { port: number }).port;
    await new Promise<void>(resolve => closed.close(() => resolve()));
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const c = new NotteClient({ baseUrl: `http://127.0.0.1:${port}`, apiKey: 'test-key', maxRetries: 2 }); // pragma: allowlist secret
    await expect(c.search('notte')).rejects.toThrow();
    expect(fetchSpy).toHaveBeenCalledTimes(3);
  });

  it('rejects an invalid maxRetries', () => {
    expect(() => client(-1)).toThrow(InvalidRequestError);
    expect(() => client(1.5)).toThrow(InvalidRequestError);
  });

  it('exposes the resolved setting', () => {
    expect(client().getConfig().maxRetries).toBe(DEFAULT_MAX_RETRIES);
    expect(client(0).getConfig().maxRetries).toBe(0);
  });
});
