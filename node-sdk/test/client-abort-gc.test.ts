import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { getEventListeners, once } from 'node:events';
import { setImmediate as nextTurn } from 'node:timers/promises';
import { setFlagsFromString } from 'node:v8';
import { runInNewContext } from 'node:vm';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { NotteClient, TIMEOUT_HEADER } from '@/client';
import { NotteTimeoutError } from '@/errors';

// Request's internal signal follower uses a WeakRef in undici. Ordinary timing
// tests miss this: collect it while the headers/body are still in flight.
setFlagsFromString('--expose_gc');
const forceGc = runInNewContext('gc') as () => void;
const collect = () => { forceGc(); forceGc(); };

describe('cancellation survives garbage collection', () => {
  let apiUrl: string;
  let handle: (req: IncomingMessage, res: ServerResponse) => void;
  const api = createServer((req, res) => handle(req, res));
  const timers = new Set<ReturnType<typeof setTimeout>>();
  const finishLater = (res: ServerResponse, body = '{"status":"ok"}', ms = 150) => {
    const timer = setTimeout(() => res.end(body), ms);
    timers.add(timer);
    res.on('close', () => { clearTimeout(timer); timers.delete(timer); });
  };
  const client = (timeoutMs = 1000) => new NotteClient({ baseUrl: apiUrl, apiKey: 'fixture', timeoutMs }); // pragma: allowlist secret
  // Run only once headers really arrived; a new turn allows weak references
  // created in the fetch turn to become collectible before aborting.
  const afterHeaders = (callback: () => void): typeof fetch => async (input, init) => {
    const response = await fetch(input, init);
    setImmediate(callback);
    return response;
  };

  beforeAll(async () => {
    vi.stubEnv('NOTTE_SDK_DISABLE_VERSION_CHECK', '1');
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    api.listen(0, '127.0.0.1');
    await once(api, 'listening');
    apiUrl = `http://127.0.0.1:${(api.address() as { port: number }).port}`;
  });
  afterEach(() => {
    for (const timer of timers) clearTimeout(timer);
    timers.clear();
  });
  afterAll(async () => {
    api.closeAllConnections();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
    await new Promise<void>(resolve => api.close(() => resolve()));
  });

  it.each(Array.from({ length: 10 }, (_, i) => i))('preserves the caller reason during a body read (%i)', async () => {
    handle = (_req, res) => {
      res.writeHead(200, { 'content-type': 'application/json' });
      res.flushHeaders();
      finishLater(res);
    };
    const controller = new AbortController();
    const reason = new Error('caller cancelled');
    const pending = client().getClient().get({
      url: '/health', signal: controller.signal,
      fetch: afterHeaders(() => { collect(); controller.abort(reason); }),
    });
    await expect(pending).rejects.toBe(reason);
  });

  it.each(['application/json', 'text/plain'])('keeps the SDK deadline during a %s body read', async contentType => {
    handle = (_req, res) => {
      res.writeHead(200, { 'content-type': contentType });
      res.flushHeaders();
      finishLater(res, '{"status":"ok"}', 500);
    };
    let collected = false;
    await expect(client(100).getClient().get({
      url: '/health', fetch: afterHeaders(() => { collect(); collected = true; }),
    })).rejects.toBeInstanceOf(NotteTimeoutError);
    expect(collected).toBe(true);
  });

  it.each([0, 1000])('aborts before headers with timeoutMs=%i', async timeoutMs => {
    const controller = new AbortController();
    const reason = new Error('cancel before headers');
    handle = (_req, res) => {
      setImmediate(() => { collect(); controller.abort(reason); });
      finishLater(res);
    };
    await expect(client(timeoutMs).getClient().get({
      url: '/health', signal: controller.signal,
    })).rejects.toBe(reason);
  });

  it('rejects an already aborted caller signal', async () => {
    const controller = new AbortController();
    const reason = new Error('already cancelled');
    controller.abort(reason);
    collect();
    await expect(client().getClient().get({ url: '/health', signal: controller.signal })).rejects.toBe(reason);
  });

  it('preserves caller cancellation through a redirect and text/plain normalization', async () => {
    handle = (req, res) => {
      if (req.url === '/redirect') {
        res.writeHead(307, { location: '/body' });
        res.end();
      } else {
        res.writeHead(200, { 'content-type': 'text/plain' });
        res.flushHeaders();
        finishLater(res);
      }
    };
    const controller = new AbortController();
    const reason = new Error('cancel redirected body');
    const transport: typeof fetch = async (input, init) => {
      const response = await fetch(input, init);
      if (response.status === 200) setImmediate(() => { collect(); controller.abort(reason); });
      return response;
    };
    await expect(client().getClient().get({
      url: '/redirect', signal: controller.signal, fetch: transport,
    })).rejects.toBe(reason);
  });

  it.each(['stream', 'auto'] as const)('keeps the caller signal alive after returning a %s response', async parseAs => {
    handle = (_req, res) => {
      res.writeHead(200, parseAs === 'stream' ? { 'content-type': 'text/event-stream' } : {});
      res.flushHeaders();
      finishLater(res, 'data: done\n\n');
    };
    const controller = new AbortController();
    const { data } = await client().getClient().get({
      url: '/stream', parseAs, signal: controller.signal,
      headers: { [TIMEOUT_HEADER]: '0' },
    });
    const reader = (data as ReadableStream<Uint8Array>).getReader();
    const read = reader.read();
    const rejected = expect(read).rejects.toMatchObject({ name: 'AbortError' });
    await nextTurn();
    collect();
    controller.abort(new DOMException('cancel live stream', 'AbortError'));
    try { await rejected; } finally { reader.releaseLock(); }
  });

  it('keeps Function.run SSE under its own deadline after GC', async () => {
    handle = (req, res) => {
      if (req.url?.endsWith('/create')) {
        res.setHeader('content-type', 'application/json');
        res.end(JSON.stringify({ function_id: 'fixture', function_run_id: 'run-1', status: 'created' }));
      } else {
        res.writeHead(200, { 'content-type': 'text/event-stream' });
        res.flushHeaders();
        finishLater(res, 'data: done\n\n', 500);
      }
    };
    let collected = false;
    const sdk = client();
    sdk.getClient().setConfig({ fetch: async (input, init) => {
      const response = await fetch(input, init);
      if (response.headers.get('content-type') === 'text/event-stream') {
        setImmediate(() => { collect(); collected = true; });
      }
      return response;
    } });
    await expect(sdk.Function({ function_id: 'fixture' }).run({}, {
      stream: true, timeoutMs: 100, onLog: () => undefined,
    })).rejects.toBeInstanceOf(NotteTimeoutError);
    expect(collected).toBe(true);
  });

  it('cancels the public SSE fetch before headers after GC', async () => {
    const controller = new AbortController();
    const reason = new Error('cancel SSE connection');
    handle = (_req, res) => {
      setImmediate(() => { collect(); controller.abort(reason); });
      finishLater(res, 'data: "too late"\n\n');
    };
    const onSseError = vi.fn();
    const transport = vi.fn<typeof fetch>((input, init) => fetch(input, init));
    const { stream } = await client().getClient().sse.get({
      url: '/sse', signal: controller.signal, fetch: transport,
      onSseError, sseMaxRetryAttempts: 1,
    });
    expect(await stream.next()).toEqual({ done: true, value: undefined });
    expect(onSseError).toHaveBeenCalledWith(reason);
    expect(transport.mock.calls[0][1]?.signal?.aborted).toBe(true);
  });

  it('keeps the public SSE deadline while reading events after GC', async () => {
    handle = (_req, res) => {
      res.writeHead(200, { 'content-type': 'text/event-stream' });
      res.flushHeaders();
      finishLater(res, 'data: "too late"\n\n', 500);
    };
    const onSseError = vi.fn();
    const { stream } = await client(100).getClient().sse.get({
      url: '/sse', fetch: afterHeaders(collect), onSseError, sseMaxRetryAttempts: 1,
    });
    expect(await stream.next()).toEqual({ done: true, value: undefined });
    expect(onSseError).toHaveBeenCalledWith(expect.objectContaining({ name: 'TimeoutError' }));
  });

  it('gives each public SSE retry a fresh deadline', async () => {
    let attempts = 0;
    handle = (_req, res) => {
      res.writeHead(200, { 'content-type': 'text/event-stream' });
      if (++attempts === 1) {
        res.flushHeaders();
        finishLater(res, 'data: "too late"\n\n', 500);
      } else res.end('data: "retried"\n\n');
    };
    const onSseError = vi.fn();
    const { stream } = await client(100).getClient().sse.get({
      url: '/sse', fetch: afterHeaders(collect), onSseError,
      sseMaxRetryAttempts: 2, sseDefaultRetryDelay: 0,
    });
    expect(await stream.next()).toEqual({ done: false, value: 'retried' });
    expect(await stream.next()).toEqual({ done: true, value: undefined });
    expect(attempts).toBe(2);
    expect(onSseError).toHaveBeenCalledTimes(1);
  });

  it('preserves streamed uploads and Request options through a custom fetch', async () => {
    let received = '';
    handle = async (req, res) => {
      for await (const chunk of req) received += chunk.toString();
      res.setHeader('content-type', 'application/json');
      res.end('{}');
    };
    const body = new ReadableStream<Uint8Array>({
      async start(controller) {
        controller.enqueue(new TextEncoder().encode('first'));
        await nextTurn();
        controller.enqueue(new TextEncoder().encode('second'));
        controller.close();
      },
    });
    const transport = vi.fn<typeof fetch>((input, init) => fetch(input, init));
    await client().getClient().post({
      url: '/upload', body, bodySerializer: null, fetch: transport,
      ...{ duplex: 'half' }, cache: 'no-store', credentials: 'omit',
      headers: { 'x-upload': 'stream' },
    });
    expect(received).toBe('firstsecond');
    const [request, init] = transport.mock.calls[0];
    expect(request).toBeInstanceOf(Request);
    expect(request).toMatchObject({ method: 'POST', duplex: 'half', cache: 'no-store', credentials: 'omit', redirect: 'manual' });
    expect((request as Request).headers.get('x-upload')).toBe('stream');
    expect(init?.signal).toBeInstanceOf(AbortSignal);
  });

  it.each([true, false])('does not accumulate listeners on a reused caller signal (AbortSignal.any=%s)', async useAny => {
    const descriptor = Object.getOwnPropertyDescriptor(AbortSignal, 'any')!;
    if (!useAny) Object.defineProperty(AbortSignal, 'any', { value: undefined, configurable: true });
    handle = (_req, res) => {
      res.setHeader('content-type', 'application/json');
      res.end('{}');
    };
    const controller = new AbortController();
    const sdk = client();
    const counts: number[] = [];
    try {
      for (let i = 0; i < 30; i++) {
        await sdk.getClient().get({ url: '/health', signal: controller.signal });
        // Undici also installs weak listeners for the generated Request. Allow
        // its FinalizationRegistry to remove those before measuring growth.
        await nextTurn();
        collect();
        await nextTurn();
        counts.push(getEventListeners(controller.signal, 'abort').length);
      }
      expect(Math.max(...counts.slice(10))).toBeLessThanOrEqual(2);
    } finally { Object.defineProperty(AbortSignal, 'any', descriptor); }
  });
});
