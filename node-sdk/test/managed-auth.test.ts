import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { NotteClient } from '@/client';
import { ManagedAuthError, type ManagedAuthOperation } from '@/managed-auth';
import { InvalidRequestError, NotteAPIError, NotteTimeoutError } from '@/errors';
import { DEFAULT_ALLOWED_PATTERNS } from '@/proxy/patterns';

const operation = (status: ManagedAuthOperation['status'] = 'running'): ManagedAuthOperation => ({
  id: 'operation-1', connection_id: 'connection-1', source: 'reauthenticate', status,
  phase: 'login', attempt: 1, auth_retry: 0, deadline: '', created_at: '', updated_at: '',
});
const session = (status = 'active') => ({ session_id: 'session-1', status, viewer_url: 'https://viewer.example/ready' });
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'content-type': 'application/json' },
});

describe('managed auth transport and lifecycle', () => {
  let calls: Request[];
  let handle: (request: Request) => Response | Promise<Response>;
  let client: NotteClient;
  beforeEach(() => {
    vi.stubEnv('NOTTE_SDK_DISABLE_VERSION_CHECK', '1');
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
    calls = [];
    handle = request => {
      if (request.method === 'DELETE') return json(session('closed'));
      if (request.url.endsWith('/sessions/start')) return json(session('authenticating'));
      if (request.url.endsWith('/auth')) return json({ session_id: 'session-1', status: 'active', operations: [] });
      if (request.url.endsWith('/sessions/session-1')) return json(session());
      throw new Error(`Unexpected request: ${request.url}`);
    };
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
      calls.push(request.clone());
      return handle(request);
    }));
    client = new NotteClient({ apiKey: 'test-key' }); // pragma: allowlist secret (test fixture)
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks(); });

  it('supports cancellation without AbortSignal.any and removes its listener', async () => {
    const originalAny = Object.getOwnPropertyDescriptor(AbortSignal, 'any');
    Object.defineProperty(AbortSignal, 'any', { configurable: true, value: undefined });
    try {
      const controller = new AbortController();
      const remove = vi.spyOn(controller.signal, 'removeEventListener');
      handle = request => request.method === 'DELETE' ? json(session('closed'))
        : request.url.endsWith('/sessions/start') ? json(session('authenticating'))
        : new Promise((_, reject) => {
          request.signal.addEventListener('abort', () => reject(request.signal.reason), { once: true });
        });
      const started = client.Session({ auth_ids: ['connection-1'] }).start({ signal: controller.signal });
      setTimeout(() => controller.abort(new Error('cancelled by caller')), 10);
      await expect(started).rejects.toThrow('cancelled by caller');
      expect(remove).toHaveBeenCalledWith('abort', expect.any(Function));
      expect(calls.filter(r => r.method === 'DELETE')).toHaveLength(1);
    } finally {
      if (originalAny) Object.defineProperty(AbortSignal, 'any', originalAny);
      else Reflect.deleteProperty(AbortSignal, 'any');
    }
  });

  it.each([500, 529])('does not retry session creation after cancellation on HTTP %s', async status => {
    const controller = new AbortController();
    handle = () => {
      if (status === 529) setTimeout(() => controller.abort(new Error('cancelled retry')), 10);
      else controller.abort(new Error('cancelled retry'));
      return json({ detail: 'capacity unavailable' }, status);
    };
    await expect(client.Session().start({ signal: controller.signal })).rejects.toThrow('cancelled retry');
    expect(calls).toHaveLength(1);
  });

  it('persists cookies when metadata fails after readiness succeeds', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'notte-auth-'));
    const cookieFile = join(directory, 'cookies.json');
    try {
      const browser = client.Session({ auth_ids: ['connection-1'], cookie_file: cookieFile });
      const cookies = [{ name: 'auth', value: 'updated', domain: 'example.com', path: '/', httpOnly: true }];
      vi.spyOn(browser, 'getCookies').mockResolvedValue(cookies);
      const original = handle;
      handle = request => request.method === 'GET' && request.url.endsWith('/sessions/session-1')
        ? json({ detail: 'metadata unavailable' }, 503) : original(request);
      await expect(browser.start({ pollIntervalMs: 1 })).rejects.toThrow();
      expect(JSON.parse(await readFile(cookieFile, 'utf8'))).toEqual(cookies);
      expect(calls.filter(r => r.method === 'DELETE')).toHaveLength(1);
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });

  it('shares one cookie upload between concurrent readiness waits', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'notte-auth-'));
    const cookieFile = join(directory, 'cookies.json');
    await writeFile(cookieFile, '[]');
    try {
      const browser = client.Session({ auth_ids: ['connection-1'], cookie_file: cookieFile });
      await browser.start({ wait_for_authentication: false });
      let release!: () => void;
      const upload = vi.spyOn(browser, 'setCookiesFromFile').mockImplementation(() => new Promise(resolve => { release = () => resolve({} as never); }));
      const waits = [browser.waitForAuth(), browser.waitForAuth()];
      await vi.waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
      release();
      await Promise.all(waits);
      expect(upload).toHaveBeenCalledTimes(1);
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });

  it('waits before use, sends bounded login retries, then closes exactly once', async () => {
    const browser = client.Session({ auth_ids: ['connection-1'], auth_retry: 2, wait_for_authentication: false });
    await browser.use(async ready => {
      expect(ready.getResponse()?.status).toBe('active');
      expect(calls.map(r => new URL(r.url).pathname)).toEqual(['/sessions/start', '/sessions/session-1/auth', '/sessions/session-1']);
    });
    expect(await calls[0].json()).toMatchObject({ auth_ids: ['connection-1'], auth_retry: 2, wait_for_authentication: false });
    expect(calls.filter(r => r.method === 'DELETE')).toHaveLength(1);
  });

  it('returns explicitly nonblocking, then waits without creating another session', async () => {
    const browser = client.Session({ auth_ids: ['connection-1'] });
    await browser.start({ wait_for_authentication: false });
    expect(calls).toHaveLength(1);
    expect(browser.getResponse()?.status).toBe('authenticating');
    await browser.waitForAuth();
    expect(browser.getResponse()?.viewer_url).toBe('https://viewer.example/ready');
    expect(calls.filter(r => r.method === 'POST')).toHaveLength(1);
  });

  it('omits auth_retry on ordinary sessions and does not poll an active start', async () => {
    handle = () => json(session());
    await client.Session({ auth_retry: 2 }).start();
    expect(await calls[0].json()).not.toHaveProperty('auth_retry');
    expect(calls).toHaveLength(1);
  });

  it.each([1, 2, 3])('retries %s final metadata failures without another start', async failures => {
    let remaining = failures;
    const original = handle;
    handle = request => request.url.endsWith('/sessions/session-1') && request.method === 'GET' && remaining-- > 0
      ? json({ error: 'temporary' }, 503) : original(request);
    const browser = client.Session({ auth_ids: ['connection-1'] });
    const started = browser.start({ pollIntervalMs: 1 });
    if (failures === 3) {
      await expect(started).rejects.toBeInstanceOf(NotteAPIError);
      expect(calls.filter(r => r.method === 'DELETE')).toHaveLength(1);
    } else {
      await started;
      expect(browser.getResponse()?.status).toBe('active');
      expect(calls.filter(r => r.method === 'DELETE')).toHaveLength(0);
    }
    expect(calls.filter(r => r.method === 'POST')).toHaveLength(1);
  });

  it('does not call the use callback after authentication fails', async () => {
    const original = handle;
    handle = request => request.url.endsWith('/auth') ? json({ status: 'failed', error: 'Invalid credentials' }) : original(request);
    const callback = vi.fn();
    await expect(client.Session({ auth_ids: ['connection-1'] }).use(callback)).rejects.toThrow('Invalid credentials');
    expect(callback).not.toHaveBeenCalled();
    expect(calls.filter(r => r.method === 'DELETE')).toHaveLength(1);
  });

  it('does not retry a readiness 403', async () => {
    const original = handle;
    handle = request => request.url.endsWith('/auth') ? json({ detail: 'Forbidden' }, 403) : original(request);
    await expect(client.Session({ auth_ids: ['connection-1'] }).start()).rejects.toBeInstanceOf(NotteAPIError);
    expect(calls.filter(r => r.url.endsWith('/auth'))).toHaveLength(1);
    expect(calls.filter(r => r.method === 'DELETE')).toHaveLength(1);
  });

  it.each(['timeout', 'abort'])('cleans up after %s during a hung readiness request', async mode => {
    const original = handle;
    handle = request => request.url.endsWith('/auth') ? new Promise((_, reject) => {
      request.signal.addEventListener('abort', () => reject(request.signal.reason), { once: true });
    }) : original(request);
    const controller = new AbortController();
    const started = client.Session({ auth_ids: ['connection-1'] }).start({ timeoutMs: 30, signal: controller.signal });
    if (mode === 'abort') setTimeout(() => controller.abort(new Error('user stopped')), 5);
    await expect(started).rejects.toThrow(mode === 'abort' ? 'user stopped' : 'Timed out waiting for authentication');
    expect(calls.filter(r => r.method === 'DELETE')).toHaveLength(1);
  });

  it('retains a cancelled in-flight creation result so it can close the session', async () => {
    const controller = new AbortController();
    const original = handle;
    handle = request => {
      if (request.url.endsWith('/sessions/start')) controller.abort(new Error('user stopped'));
      return original(request);
    };
    await expect(client.Session({ auth_ids: ['connection-1'] }).start({ signal: controller.signal })).rejects.toThrow('user stopped');
    expect(calls.filter(r => r.method === 'DELETE')).toHaveLength(1);
  });

  it.each(['refreshConnection', 'reauthenticateConnection'] as const)('%s posts once, then polls through the bound client', async method => {
    handle = request => request.method === 'POST' ? json(operation(), 202) : json(operation('succeeded'));
    const result = await client.managedAuth[method]('connection-1', { auth_retry: 2, pollIntervalMs: 1 });
    expect(result.status).toBe('succeeded');
    expect(await calls[0].json()).toEqual({ auth_retry: 2 });
    expect(calls[0].headers.get('Authorization')).toBe('Bearer test-key');
    expect(calls[1].url).toBe('https://api.notte.cc/managed-auth/operations/operation-1');
    expect(calls.filter(r => r.method === 'POST')).toHaveLength(1);
  });

  it('returns an accepted operation without polling when wait is false', async () => {
    handle = () => json(operation(), 202);
    expect((await client.managedAuth.refreshConnection('connection-1', { wait: false })).status).toBe('running');
    expect(calls).toHaveLength(1);
  });

  it('keeps check verifier-only', async () => {
    handle = () => json({ connection_id: 'connection-1', authenticated: false, status: 'needs_reauth', message: 'Rejected' });
    expect((await client.managedAuth.checkConnection('connection-1')).authenticated).toBe(false);
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toMatch(/\/check$/);
  });

  it('surfaces a conflicting login without retrying or tracking another operation', async () => {
    handle = () => json({ detail: 'Already authenticating', operation_id: 'other' }, 409);
    await expect(client.managedAuth.reauthenticateConnection('connection-1')).rejects.toMatchObject({ statusCode: 409 });
    expect(calls).toHaveLength(1);
  });

  it.each(['failed', 'cancelled'] as const)('rejects a %s operation', async status => {
    await expect(client.managedAuth.waitForAuth({ ...operation(status), error: 'Login ended' })).rejects.toBeInstanceOf(ManagedAuthError);
    expect(calls).toHaveLength(0);
  });

  it('bounds operation waiting even when it remains pending', async () => {
    handle = () => json(operation());
    await expect(client.managedAuth.waitForAuth(operation(), { timeoutMs: 15, pollIntervalMs: 1 })).rejects.toBeInstanceOf(NotteTimeoutError);
    expect(calls.every(r => r.method === 'GET')).toBe(true);
  });

  it.each([-1, 3, 0.5])('rejects invalid auth_retry %s before sending a request', async auth_retry => {
    await expect(client.Session({ auth_ids: ['connection-1'], auth_retry }).start()).rejects.toBeInstanceOf(InvalidRequestError);
    await expect(client.managedAuth.refreshConnection('connection-1', { auth_retry })).rejects.toBeInstanceOf(InvalidRequestError);
    expect(calls).toHaveLength(0);
  });

  it.each(['sessions/session-1/auth', 'managed-auth/operations/operation-1', 'managed-auth/connections/connection-1/check', 'managed-auth/connections/connection-1/refresh', 'managed-auth/connections/connection-1/reauthenticate'])('allows %s through the SDK proxy', path => {
    expect(DEFAULT_ALLOWED_PATTERNS.some(pattern => pattern.test(path))).toBe(true);
    expect(DEFAULT_ALLOWED_PATTERNS.some(pattern => pattern.test(`${path}/unexpected`))).toBe(false);
  });
});
