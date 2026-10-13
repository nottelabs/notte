import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { once } from 'node:events';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { NotteClient } from '@/client';
import { NotteTimeoutError } from '@/errors';

describe('client HTTP boundaries', () => {
  let apiUrl: string;
  let runtimeUrl: string;
  let runtime: (req: IncomingMessage, res: ServerResponse) => void;
  const api = createServer((req, res) => {
    if (req.url === '/health') {
      res.writeHead(200, { 'content-type': 'application/json' });
      res.flushHeaders();
      setTimeout(() => res.end('{"status":"ok"}'), 150);
    } else if (req.url === '/raw-stream') {
      res.writeHead(200);
      res.flushHeaders();
      setTimeout(() => res.end('streamed'), 150);
    } else if (req.url?.endsWith('/create')) {
      res.setHeader('content-type', 'application/json');
      res.end(JSON.stringify({ function_id: 'fixture', function_run_id: 'run-1', status: 'created' }));
    } else {
      res.writeHead(307, { location: `${runtimeUrl}/execute` });
      res.end();
    }
  });
  const target = createServer((req, res) => runtime(req, res));
  beforeAll(async () => {
    vi.stubEnv('NOTTE_SDK_DISABLE_VERSION_CHECK', '1');
    api.listen(0, '127.0.0.1');
    target.listen(0, '127.0.0.1');
    await Promise.all([once(api, 'listening'), once(target, 'listening')]);
    apiUrl = `http://127.0.0.1:${(api.address() as { port: number }).port}`;
    runtimeUrl = `http://127.0.0.1:${(target.address() as { port: number }).port}`;
  });
  afterAll(async () => {
    vi.unstubAllEnvs();
    for (const server of [api, target]) {
      server.closeAllConnections();
      await new Promise<void>(resolve => server.close(() => resolve()));
    }
  });
  const client = (timeoutMs = 1000) => new NotteClient({ baseUrl: apiUrl, apiKey: 'test-key', timeoutMs }); // pragma: allowlist secret

  it.each([true, false])('authenticates a cross-origin runtime and preserves its body (stream=%s)', async stream => {
    let headers: IncomingMessage['headers'] = {};
    let body: any;
    runtime = async (req, res) => {
      headers = req.headers;
      const chunks = [];
      for await (const chunk of req) chunks.push(chunk);
      body = JSON.parse(Buffer.concat(chunks).toString());
      const result = { function_id: 'fixture', function_run_id: 'run-1', status: 'closed', result: { echo: 'ok' } };
      res.setHeader('content-type', 'text/plain');
      res.end(stream ? `data: ${JSON.stringify({ type: 'result', message: JSON.stringify(result) })}\n\n` : JSON.stringify(result));
    };
    const result = await client().NotteFunction({ function_id: 'fixture' }).run({ value: 'ok' }, { stream });
    expect(result.result).toEqual({ echo: 'ok' });
    expect(body).toMatchObject({ variables: { value: 'ok' }, function_run_id: 'run-1', stream });
    expect(headers.authorization).toBeUndefined();
    expect(headers['x-notte-api-key']).toBe('test-key'); // pragma: allowlist secret
  });

  it('does not delegate credentials from unrelated API endpoints', async () => {
    let headers: IncomingMessage['headers'] = {};
    runtime = (req, res) => { headers = req.headers; res.end('{}'); };
    await client().getClient().post({ url: '/unrelated', headers: { 'x-notte-api-key': 'test-key' } }); // pragma: allowlist secret
    expect(headers.authorization).toBeUndefined();
    expect(headers['x-notte-api-key']).toBeUndefined();
  });

  it('does not forward the runtime key through another redirect', async () => {
    const headers: IncomingMessage['headers'][] = [];
    runtime = (req, res) => {
      headers.push(req.headers);
      if (req.url === '/execute') {
        res.writeHead(308, { location: '/second' });
        res.end();
      } else res.end('{}');
    };
    await client().getClient().post({ url: '/functions/fixture/runs/run-1', headers: { 'x-notte-api-key': 'test-key' } }); // pragma: allowlist secret
    expect(headers[0]['x-notte-api-key']).toBe('test-key'); // pragma: allowlist secret
    expect(headers[1]['x-notte-api-key']).toBeUndefined();
  });

  it('times out while reading a body after headers have arrived', async () => {
    await expect(client(40).healthCheck()).rejects.toBeInstanceOf(NotteTimeoutError);
  });

  it('keeps the deadline through a redirect and its response body', async () => {
    runtime = (_req, res) => {
      res.writeHead(200, { 'content-type': 'application/json' });
      res.flushHeaders();
      setTimeout(() => res.end('{}'), 150);
    };
    await expect(client(40).getClient().get({ url: '/redirect' })).rejects.toBeInstanceOf(NotteTimeoutError);
  });

  it('preserves caller cancellation while reading the response body', async () => {
    const controller = new AbortController();
    const reason = new Error('caller cancelled');
    const pending = client().getClient().get({ url: '/health', signal: controller.signal });
    const timer = setTimeout(() => controller.abort(reason), 40);
    try { await expect(pending).rejects.toBe(reason); } finally { clearTimeout(timer); }
  });

  it('does not buffer an automatically detected stream', async () => {
    const response = await client(40).getClient().get({ url: '/raw-stream', parseAs: 'auto' });
    expect(response.data).toBeInstanceOf(ReadableStream);
    expect(await new Response(response.data as ReadableStream).text()).toBe('streamed');
  });

  it('allows a body to finish before its deadline', async () => {
    await expect(client().getClient().get({ url: '/health' })).resolves.toMatchObject({ data: { status: 'ok' } });
  });
});
