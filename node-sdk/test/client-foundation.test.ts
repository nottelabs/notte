/**
 * Transport-level behaviour of NotteClient, the counterpart of
 * tests/sdk/test_client.py, test_db_preview_routing.py and
 * test_base_client_version_check.py: typed errors, timeouts, headers,
 * preview-branch routing, health check and list namespaces.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ACCEPT_RUN_STATUSES_HEADER, DEFAULT_NOTTE_API_URL, NotteClient, TIMEOUT_HEADER } from '@/client';
import { clientUserAgent, githubActionsContext } from '@/client-info';
import { AuthenticationError, InvalidRequestError, NotteAPIError, NotteAPIExecutionError, NotteTimeoutError } from '@/errors';
import { SDK_VERSION } from '@/version';
import { checkForLatestVersion, resetVersionCheckForTests } from '@/version-check';

// Development builds never suggest upgrades (like `.dev` versions in Python), so pin a published version.
vi.mock('@/version', () => ({ SDK_VERSION: '1.0.0', SDK_PACKAGE_NAME: 'notte-sdk' }));

type FetchImpl = (request: Request) => Promise<Response>;

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  const headers = new Headers(init.headers);
  headers.set('content-type', 'application/json');
  return new Response(JSON.stringify(body), { status: 200, ...init, headers });
}

function stubFetch(impl: FetchImpl): { requests: Request[] } {
  const requests: Request[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (request: Request) => {
      requests.push(request);
      return impl(request);
    }),
  );
  return { requests };
}

const API_KEY = 'test-api-key'; // pragma: allowlist secret

describe('NotteClient transport', () => {
  let warn: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    resetVersionCheckForTests();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    warn.mockRestore();
  });

  describe('construction', () => {
    it('raises AuthenticationError without an API key, like the Python client', () => {
      vi.stubEnv('NOTTE_API_KEY', '');
      expect(() => new NotteClient({ baseUrl: DEFAULT_NOTTE_API_URL })).toThrow(AuthenticationError);
    });

    it('rejects insecure remote URLs with InvalidRequestError', () => {
      expect(() => new NotteClient({ apiKey: API_KEY, baseUrl: 'http://remote.example' })).toThrow(InvalidRequestError);
    });

    it('rejects a negative timeout', () => {
      expect(() => new NotteClient({ apiKey: API_KEY, timeoutMs: -1 })).toThrow(InvalidRequestError);
    });

    it('warns when the server URL is not the default, like Python', () => {
      new NotteClient({ apiKey: API_KEY, baseUrl: 'https://us-staging.notte.cc' });
      expect(warn).toHaveBeenCalledWith('NOTTE_API_URL is set to: https://us-staging.notte.cc');
      warn.mockClear();
      new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL });
      expect(warn).not.toHaveBeenCalled();
    });

    it('resolves defaults into getConfig()', () => {
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL });
      expect(client.getConfig()).toEqual({
        apiKey: API_KEY,
        baseUrl: DEFAULT_NOTTE_API_URL,
        maxRetries: 3,
        timeoutMs: 60_000,
        captchaTimeoutSeconds: 180,
        dbPreview: undefined,
        verbose: false,
      });
    });
  });

  describe('request headers', () => {
    it('sends the bearer token, sdk origin and version like Python', async () => {
      const { requests } = stubFetch(async () => jsonResponse({ status: 'ok' }));
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL });

      await client.healthCheck();

      expect(requests).toHaveLength(1);
      const headers = requests[0].headers;
      expect(requests[0].url).toBe(`${DEFAULT_NOTTE_API_URL}/health`);
      expect(headers.get('authorization')).toBe(`Bearer ${API_KEY}`);
      expect(headers.get('x-notte-request-origin')).toBe('sdk-node');
      expect(headers.get('x-notte-sdk-version')).toBe(SDK_VERSION);
      expect(headers.get('x-db-preview')).toBeNull();
      expect(headers.get(TIMEOUT_HEADER)).toBeNull();
      expect(headers.get('user-agent')).toBe(clientUserAgent());
      expect(headers.get('user-agent')).toMatch(new RegExp(`^notte-sdk-node/${SDK_VERSION} \\(node `));
    });

    it('names the GitHub Actions job in the user agent', () => {
      const env = {
        GITHUB_ACTIONS: 'true',
        GITHUB_REPOSITORY: 'acme/shop',
        GITHUB_RUN_ID: '123456',
        GITHUB_RUN_ATTEMPT: '2',
        GITHUB_JOB: 'e2e tests\r\nX-Injected: 1',
      };
      expect(githubActionsContext(env)).toBe('github-actions (repo=acme/shop; run=123456/2; job=e2e_tests__X-Injected__1)');
      expect(githubActionsContext({ GITHUB_REPOSITORY: 'acme/shop' })).toBeUndefined();
    });

    it('no preview header by default, preview branch sent as a header when configured', async () => {
      const { requests } = stubFetch(async () => jsonResponse({ status: 'ok' }));
      vi.stubEnv('NOTTE_DB_PREVIEW_BRANCH', 'feature/my-branch');
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL });

      await client.healthCheck();

      expect(requests[0].headers.get('x-db-preview')).toBe('feature/my-branch');
    });

    it('explicit dbPreview wins over the environment', async () => {
      const { requests } = stubFetch(async () => jsonResponse({ status: 'ok' }));
      vi.stubEnv('NOTTE_DB_PREVIEW_BRANCH', 'env-branch');
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL, dbPreview: 'explicit' });

      await client.healthCheck();

      expect(requests[0].headers.get('x-db-preview')).toBe('explicit');
    });
  });

  describe('accepting the rejected run status', () => {
    // Without the header the API reports a rejected run as `failed`, so the
    // SDK opts in on every functions request, like the Python functions client.
    const get = (client: NotteClient, url: string) => client.getClient().get({ url, throwOnError: false });

    it('opts in on functions requests only', async () => {
      const { requests } = stubFetch(async () => jsonResponse({}));
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL });

      await get(client, '/functions');
      await get(client, '/functions/fn-1/runs/run-1');
      await get(client, '/sessions');
      await get(client, '/functions-like');

      expect(requests.map(r => [new URL(r.url).pathname, r.headers.get(ACCEPT_RUN_STATUSES_HEADER)])).toEqual([
        ['/functions', 'rejected'],
        ['/functions/fn-1/runs/run-1', 'rejected'],
        ['/sessions', null],
        ['/functions-like', null],
      ]);
    });

    it('follows a base URL with a path prefix', async () => {
      const { requests } = stubFetch(async () => jsonResponse({}));
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: 'https://gateway.example.com/notte' });

      await get(client, '/functions/fn-1');
      await get(client, '/sessions');

      expect(requests.map(r => r.headers.get(ACCEPT_RUN_STATUSES_HEADER))).toEqual(['rejected', null]);
    });

    it("keeps a caller's own value", async () => {
      const { requests } = stubFetch(async () => jsonResponse({}));
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL });

      await client.getClient().get({ url: '/functions', throwOnError: false, headers: { [ACCEPT_RUN_STATUSES_HEADER]: 'none' } });

      expect(requests[0].headers.get(ACCEPT_RUN_STATUSES_HEADER)).toBe('none');
    });

    it('sends it on the run request of NotteFunction.run()', async () => {
      const { requests } = stubFetch(async request =>
        new URL(request.url).pathname.endsWith('/runs/create')
          ? jsonResponse({ function_id: 'fn-1', function_run_id: 'run-1', created_at: '2026-01-01T00:00:00Z', status: 'created' })
          : jsonResponse({ function_id: 'fn-1', function_run_id: 'run-1', session_id: null, status: 'closed', result: { ok: true } }),
      );
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL });

      await client.NotteFunction({ function_id: 'fn-1' }).run({}, { stream: false });

      expect(requests.map(r => r.headers.get(ACCEPT_RUN_STATUSES_HEADER))).toEqual(['rejected', 'rejected']);
    });
  });

  describe('withDbPreview', () => {
    it('leaves websocket urls untouched without a preview branch', () => {
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL });
      expect(client.withDbPreview('wss://api.notte.cc/sessions/x/debug/logs?token=abc')).toBe(
        'wss://api.notte.cc/sessions/x/debug/logs?token=abc',
      );
    });

    it('appends db_preview to websocket urls when a branch is configured', () => {
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL, dbPreview: 'feature/my-branch' });
      const url = new URL(client.withDbPreview('wss://api.notte.cc/sessions/x/debug/logs?token=abc'));
      expect(url.searchParams.get('token')).toBe('abc');
      expect(url.searchParams.get('db_preview')).toBe('feature/my-branch');
    });
  });

  describe('typed errors', () => {
    it('rejects with NotteAPIError carrying status code, path and body', async () => {
      stubFetch(async () => jsonResponse({ message: 'nope', status: 404 }, { status: 404 }));
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL });

      const error = await client.healthCheck().catch((e: unknown) => e);

      expect(error).toBeInstanceOf(NotteAPIError);
      const apiError = error as NotteAPIError;
      expect(apiError.statusCode).toBe(404);
      expect(apiError.path).toBe('/health');
      expect(apiError.error).toEqual({ message: 'nope', status: 404 });
      expect(apiError.apiMessage).toBe('nope');
    });

    it('rejects with NotteAPIError for non-JSON bodies', async () => {
      stubFetch(async () => new Response('<html>Bad gateway</html>', { status: 502, headers: { 'content-type': 'text/html' } }));
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL, maxRetries: 0 });

      const error = (await client.healthCheck().catch((e: unknown) => e)) as NotteAPIError;

      expect(error).toBeInstanceOf(NotteAPIError);
      expect(error.statusCode).toBe(502);
      expect(error.error).toEqual({ message: '<html>Bad gateway</html>' });
    });

    it('maps the x-error-class header to NotteAPIExecutionError', async () => {
      stubFetch(async () =>
        jsonResponse({ message: 'execution failed' }, { status: 400, headers: { 'x-error-class': 'NotteApiExecutionError' } }),
      );
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL });

      const error = await client.healthCheck().catch((e: unknown) => e);

      expect(error).toBeInstanceOf(NotteAPIExecutionError);
      expect(error).toBeInstanceOf(NotteAPIError);
    });

    it('adds the upgrade suggestion to 422 schema errors when a newer version is known', async () => {
      await checkForLatestVersion({
        currentVersion: '1.0.0',
        fetchFn: (async () => ({ ok: true, json: async () => ({ version: '9.9.9' }) })) as unknown as typeof fetch,
        warnFn: () => undefined,
        env: {},
      });
      stubFetch(async () => jsonResponse({ message: 'Extra inputs are not permitted: extra_forbidden' }, { status: 422 }));
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL });

      const error = (await client.healthCheck().catch((e: unknown) => e)) as NotteAPIError;

      expect(error.statusCode).toBe(422);
      expect(error.apiMessage).toContain('API returned 422 validation error');
      expect(error.apiMessage).toContain("npm install notte-sdk@9.9.9");
      expect(error.apiMessage).toContain('Original error: Extra inputs are not permitted');
    });

    it('leaves 422 errors alone when they do not look like schema mismatches', async () => {
      await checkForLatestVersion({
        currentVersion: '1.0.0',
        fetchFn: (async () => ({ ok: true, json: async () => ({ version: '9.9.9' }) })) as unknown as typeof fetch,
        warnFn: () => undefined,
        env: {},
      });
      stubFetch(async () => jsonResponse({ message: 'url must be absolute' }, { status: 422 }));
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL });

      const error = (await client.healthCheck().catch((e: unknown) => e)) as NotteAPIError;

      expect(error.apiMessage).toBe('url must be absolute');
    });
  });

  describe('timeouts', () => {
    it('aborts requests after timeoutMs and rejects with NotteTimeoutError', async () => {
      stubFetch(
        request =>
          new Promise<Response>((_, reject) => {
            request.signal.addEventListener('abort', () => reject(request.signal.reason));
          }),
      );
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL, timeoutMs: 20 });

      const error = await client.healthCheck().catch((e: unknown) => e);

      expect(error).toBeInstanceOf(NotteTimeoutError);
      expect((error as Error).message).toContain('/health');
      expect((error as Error).message).toContain('timed out after 20ms');
    });

    it('honours the per-call timeout header and strips it from the outgoing request', async () => {
      const { requests } = stubFetch(
        request =>
          new Promise<Response>((_, reject) => {
            request.signal.addEventListener('abort', () => reject(request.signal.reason));
          }),
      );
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL, timeoutMs: 60_000 });

      const error = await client
        .getClient()
        .get({ url: '/health', headers: { [TIMEOUT_HEADER]: '20' } })
        .catch((e: unknown) => e);

      expect(error).toBeInstanceOf(NotteTimeoutError);
      expect((error as Error).message).toContain('timed out after 20ms');
      expect(requests[0].headers.get(TIMEOUT_HEADER)).toBeNull();
    });

    it('a timeout of 0 disables the deadline', async () => {
      const { requests } = stubFetch(async () => jsonResponse({ status: 'ok' }));
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL, timeoutMs: 0 });

      await client.healthCheck();

      expect(requests[0].signal.aborted).toBe(false);
    });
  });

  describe('list namespaces', () => {
    it.each([
      ['sessions', '/sessions', { only_active: true, page_size: 5 }],
      ['vaults', '/vaults', { page: 2 }],
      ['functions', '/functions', { include_system: true }],
    ] as const)('client.%s.list unwraps items and forwards the query', async (namespace, path, query) => {
      const { requests } = stubFetch(async () => jsonResponse({ items: [{ id: 1 }, { id: 2 }], page: 1, page_size: 10, has_next: false, has_previous: false }));
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL });

      const items = await client[namespace].list(query as never);

      expect(items).toEqual([{ id: 1 }, { id: 2 }]);
      const url = new URL(requests[0].url);
      expect(url.pathname).toBe(path);
      for (const [key, value] of Object.entries(query)) {
        expect(url.searchParams.get(key)).toBe(String(value));
      }
    });
  });
});

describe('caller cancellation vs deadline', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('does not report a caller abort as a NotteTimeoutError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (request: Request) =>
          new Promise<Response>((_, reject) => {
            // like undici: an already-aborted signal rejects immediately
            if (request.signal.aborted) reject(request.signal.reason);
            request.signal.addEventListener('abort', () => reject(request.signal.reason));
          }),
      ),
    );
    const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL, timeoutMs: 60_000 });
    const controller = new AbortController();
    const pending = client.getClient().get({ url: '/health', signal: controller.signal }).catch((e: unknown) => e);
    controller.abort(new DOMException('cancelled by caller', 'AbortError'));

    const error = await pending;
    expect(error).not.toBeInstanceOf(NotteTimeoutError);
    expect((error as Error).name).toBe('AbortError');
  });
});

describe('deadline timer lifecycle', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('releases the deadline timer as soon as the request completes', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ status: 'ok' })));
    const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL, timeoutMs: 60_000 });
    const before = vi.getTimerCount();

    await client.healthCheck();

    expect(vi.getTimerCount()).toBe(before);
  });

  it('releases the deadline timer when the request fails', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ message: 'nope' }, { status: 500 })));
    const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL, timeoutMs: 60_000 });
    const before = vi.getTimerCount();

    await client.healthCheck().catch(() => undefined);

    expect(vi.getTimerCount()).toBe(before);
  });
});
