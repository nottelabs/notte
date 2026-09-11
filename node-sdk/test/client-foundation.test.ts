/**
 * Transport-level behaviour of NotteClient, the counterpart of
 * tests/sdk/test_client.py, test_db_preview_routing.py and
 * test_base_client_version_check.py: typed errors, timeouts, headers,
 * preview-branch routing, health check and list namespaces.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_NOTTE_API_URL, NotteClient, TIMEOUT_HEADER } from '@/client';
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
        timeoutMs: 60_000,
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
      const client = new NotteClient({ apiKey: API_KEY, baseUrl: DEFAULT_NOTTE_API_URL });

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
      ['agents', '/agents', { only_saved: true }],
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
