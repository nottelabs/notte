import { afterEach, expect, it, vi } from 'vitest';
import { NotteClient, NotteAPIError, sessionStop } from '@/index';

afterEach(() => vi.unstubAllGlobals());
const client = () => new NotteClient({ baseUrl: 'https://api.example.test', apiKey: 'test-key' }); // pragma: allowlist secret

it('binds a detached stop method to the owning client and unwraps its response', async () => {
  const requests: Request[] = [];
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    requests.push(request);
    return Response.json({ status: 'closed', session_id: 'session/id' });
  }));
  const { stop } = client().sessions;
  const result = await stop('session/id', { close_reason: 'manual' });
  expect(result.status).toBe('closed');
  expect(requests[0].method).toBe('DELETE');
  expect(requests[0].url).toBe('https://api.example.test/sessions/session%2Fid/stop?close_reason=manual');
  expect(requests[0].headers.get('authorization')).toBe('Bearer test-key');
});

it('keeps separate client credentials and URLs isolated', async () => {
  const requests: Request[] = [];
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    requests.push(request);
    return Response.json({ status: 'closed' });
  }));
  const second = new NotteClient({ baseUrl: 'https://second.example.test', apiKey: 'other-key' }); // pragma: allowlist secret
  await Promise.all([client().sessions.stop('one'), second.sessions.stop('two')]);
  expect(requests.map(request => [request.url, request.headers.get('authorization')])).toEqual([
    ['https://api.example.test/sessions/one/stop', 'Bearer test-key'],
    ['https://second.example.test/sessions/two/stop', 'Bearer other-key'],
  ]);
});

it('forwards a vault creation body and function fork ID without transport boilerplate', async () => {
  const requests: Request[] = [];
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    requests.push(request);
    return Response.json({ vault_id: 'vault', function_id: 'copy' });
  }));
  const api = client();
  expect((await api.vaults.create({ name: 'default' })).vault_id).toBe('vault');
  expect((await api.functions.fork('source')).function_id).toBe('copy');
  expect(await requests[0].json()).toEqual({ name: 'default' });
  expect(requests[1].url).toBe('https://api.example.test/functions/source/fork');
  expect(requests.map(request => request.method)).toEqual(['POST', 'POST']);
});

it('keeps list array results and the existing standalone operation API', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({ items: [{ session_id: 'one' }] })));
  const api = client();
  expect(await api.sessions.list()).toEqual([{ session_id: 'one' }]);
  expect(await sessionStop({ client: api.getClient(), path: { session_id: 'one' } })).toHaveProperty('data');
});

it('binds the required function-run header without asking the caller for credentials', async () => {
  const requests: Request[] = [];
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    requests.push(request);
    return Response.json({ status: 'closed' });
  }));
  await client().functions.runStart('function', { workflow_id: 'function', variables: {}, stream: false });
  expect(requests[0].headers.get('x-notte-api-key')).toBe('test-key');
  expect(requests[0].headers.get('authorization')).toBe('Bearer test-key');
});

it('forwards required payment headers through the generated transport', async () => {
  const requests: Request[] = [];
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    requests.push(request);
    return Response.json({ id: 'payment', status: 'pending' });
  }));
  const body = { amount: '1.00', currency: 'USD', merchant_url: 'https://example.test', merchant_name: 'Example', description: 'Test', mode: 'test' as const };
  const result = await client().sessions.createPayment('session', body, undefined, {
    headers: { 'idempotency-key': 'retry-key' },
  });
  expect(result.id).toBe('payment');
  expect(requests[0].method).toBe('POST');
  expect(requests[0].url).toBe('https://api.example.test/sessions/session/payments');
  expect(requests[0].headers.get('idempotency-key')).toBe('retry-key');
  expect(requests[0].headers.get('authorization')).toBe('Bearer test-key');
  expect(await requests[0].json()).toEqual(body);
});

it('retains generated multipart serialization for uploads', async () => {
  const requests: Request[] = [];
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    requests.push(request);
    return Response.json({ id: 'file' });
  }));
  await client().sessions.uploadSessionFile('session', { file: new Blob(['fixture']) });
  expect(requests[0].headers.get('content-type')).toMatch(/^multipart\/form-data; boundary=/);
  const form = await requests[0].formData();
  expect(await (form.get('file') as Blob).text()).toBe('fixture');
});

// These calls are intentionally never executed; tsc guards the public signatures.
if (false) {
  const body = { amount: 1, currency: 'USD', merchant_url: 'https://example.test', merchant_name: 'Example', description: 'Test', mode: 'test' as const };
  void client().sessions.createPayment('session', body, undefined, { headers: { 'idempotency-key': 'retry-key' } });
  // @ts-expect-error Required payment headers cannot be omitted.
  void client().sessions.createPayment('session', body);
  // @ts-expect-error The idempotency key is required.
  void client().sessions.createPayment('session', body, undefined, { headers: {} });
  // @ts-expect-error Authentication remains bound to the client.
  void client().sessions.createPayment('session', body, undefined, { headers: { 'idempotency-key': 'retry-key', 'x-notte-api-key': 'override' } });
  // @ts-expect-error Session ID is required.
  void client().sessions.stop();
  // @ts-expect-error IDs are strings, not numbers.
  void client().functions.fork(1);
  // @ts-expect-error Invalid vault request field.
  void client().vaults.create({ nonexistent: true });
}

it('preserves typed API errors', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({ detail: 'missing' }, { status: 404 })));
  await expect(client().sessions.stop('missing')).rejects.toBeInstanceOf(NotteAPIError);
});

it('forwards cancellation', async () => {
  const controller = new AbortController();
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    controller.abort();
    expect(request.signal.aborted).toBe(true);
    throw new DOMException('Aborted', 'AbortError');
  }));
  await expect(client().sessions.stop('one', undefined, { signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' });
});
