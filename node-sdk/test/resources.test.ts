import { afterEach, expect, it, vi } from 'vitest';
import { NotteClient, NotteAPIError, sessionStop, type GetFunctionRunResponseWritable } from '@/index';

afterEach(() => vi.unstubAllGlobals());
const client = () => new NotteClient({ baseUrl: 'https://api.example.test', apiKey: 'test-key' }); // pragma: allowlist secret

it.each(['files', 'sessions'] as const)('executes a file action through %s with a pinned target', async resource => {
  const requests: Request[] = [];
  const action = { type: 'upload_file' as const, file_path: 'input.txt', selector: 'input[type=file]' };
  const payload = { success: true, action, message: 'Uploaded', started_at: '2026-10-20T00:00:00Z', ended_at: '2026-10-20T00:00:01Z' };
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    requests.push(request);
    return Response.json(payload);
  }));
  const api = client();
  const execute = resource === 'files' ? api.files.execute : api.sessions.executeSessionFile;
  const result = await execute('session/id', { action, target_id: 'browser-target', record: false }, { update_metadata: false });
  expect(result).toEqual(payload);
  expect(requests).toHaveLength(1);
  expect(requests[0].method).toBe('POST');
  expect(requests[0].url).toBe('https://api.example.test/sessions/session%2Fid/page/execute/file?update_metadata=false');
  expect(requests[0].headers.get('authorization')).toBe('Bearer test-key');
  expect(await requests[0].json()).toEqual({ action, target_id: 'browser-target', record: false });
});

it('preserves function artifact and execution runtime metadata', async () => {
  const payload = { sdk_generation: 'v110', artifact_sdk_generation: 'v19', status: 'active' };
  vi.stubGlobal('fetch', vi.fn(async () => Response.json(payload)));
  const result = await client().functions.runGetMetadata('function', 'run');
  expect(result.sdk_generation).toBe('v110');
  expect(result.artifact_sdk_generation).toBe('v19');
});

it('keeps runtime-health cancellation options before the SDK-generation query', async () => {
  const controller = new AbortController();
  const requests: Request[] = [];
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    requests.push(request);
    return Response.json({ status: 'healthy' });
  }));
  const api = client();
  const options = { signal: controller.signal, headers: { 'x-notte-request-origin': 'compatibility-test' } };
  await api.functions.runtimeHealth(options);
  await api.functions.runtimeHealth(options, { sdk_generation: 'v110' });
  expect(requests[0].url).toBe('https://api.example.test/functions/health');
  expect(requests[1].url).toBe('https://api.example.test/functions/health?sdk_generation=v110');
  for (const request of requests) {
    expect(request.headers.get('x-notte-request-origin')).toBe('sdk-node');
    expect(request.signal.aborted).toBe(false);
  }
  controller.abort();
  expect(requests.every(request => request.signal.aborted)).toBe(true);
});

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

it('preserves third-argument run request options and accepts a payload query afterward', async () => {
  const requests: Request[] = [];
  const controller = new AbortController();
  const run: GetFunctionRunResponseWritable = {
    function_id: 'function', function_run_id: 'run', status: 'closed',
    created_at: '2026-10-06T00:00:00Z', updated_at: '2026-10-06T00:00:00Z',
  };
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    requests.push(request);
    return Response.json(run);
  }));
  const api = client();
  const options = { signal: controller.signal, headers: { 'x-notte-request-origin': 'compatibility-test' } };
  expect(await api.functions.runGetMetadata('function', 'run', options)).toEqual(run);
  await api.functions.runGetMetadata('function', 'run', options, { payload_mode: 'references' });
  expect(requests[0].url).toBe('https://api.example.test/functions/function/runs/run');
  expect(requests[1].url).toBe('https://api.example.test/functions/function/runs/run?payload_mode=references');
  for (const request of requests) {
    expect(request.headers.get('x-notte-request-origin')).toBe('sdk-node');
    expect(request.signal.aborted).toBe(false);
  }
  controller.abort();
  expect(requests.every(request => request.signal.aborted)).toBe(true);
});


it.each(['create', 'list'] as const)('delegates invalid profile %s values to the API', async method => {
  const requests: Request[] = [];
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    requests.push(request);
    return Response.json({ detail: 'invalid profile input' }, { status: 422 });
  }));
  const api = client();
  const data = method === 'create' ? { name: 42 } : { page: -1 };
  const error = await api.profiles[method](data as never).catch((value: unknown) => value);
  expect(error).toBeInstanceOf(NotteAPIError);
  expect(error).toMatchObject({ statusCode: 422 });
  expect(requests).toHaveLength(1);
  if (method === 'create') expect(await requests[0].json()).toEqual(data);
  else expect(new URL(requests[0].url).searchParams.get('page')).toBe('-1');
});

it.each(['text/plain', 'application/json'])('preserves %s download bytes through both file entry points', async contentType => {
  const bytes = contentType === 'text/plain' ? 'plain file content' : '{ "keep": "spacing" }';
  vi.stubGlobal('fetch', vi.fn(async () => new Response(bytes, { headers: { 'content-type': contentType } })));
  const api = client();
  for (const download of [api.files.download, api.sessions.downloadSessionFile]) {
    const result = await download('session', 'file');
    expect(result).toBeInstanceOf(Blob);
    expect(await (result as Blob).text()).toBe(bytes);
  }
});


it('returns successful raw payload objects with a detail key and preserves HTTP errors', async () => {
  const fetch = vi.fn(async () => Response.json({ detail: 'notes' }));
  vi.stubGlobal('fetch', fetch);
  const api = client();
  expect(await api.functions.downloadRunPayload('function', 'run', 'variables')).toEqual({ detail: 'notes' });
  fetch.mockImplementation(async () => Response.json({ detail: 'missing' }, { status: 404 }));
  await expect(api.functions.downloadRunPayload('function', 'run', 'variables')).rejects.toBeInstanceOf(NotteAPIError);
});

it.each([true, false])('sends explicit sharing=%s through the metadata operation', async shared => {
  const requests: Request[] = [];
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    requests.push(request);
    return Response.json({ function_id: 'function', shared });
  }));
  const result = await client().functions.metadataUpdate('function', { shared });
  expect(result.shared).toBe(shared);
  expect(requests).toHaveLength(1);
  expect(requests[0].method).toBe('PATCH');
  expect(requests[0].url).toBe('https://api.example.test/functions/function');
  expect(await requests[0].json()).toEqual({ shared });
});

it('leaves sharing absent from unrelated metadata updates', async () => {
  const requests: Request[] = [];
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    requests.push(request);
    return Response.json({ function_id: 'function', shared: true });
  }));
  expect((await client().functions.metadataUpdate('function', { name: 'renamed' })).shared).toBe(true);
  expect(await requests[0].json()).toEqual({ name: 'renamed' });
});
