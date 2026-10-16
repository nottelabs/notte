import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NotteClient } from '@/client';
import { NotteAPIError } from '@/errors';

describe('vault validation at the HTTP boundary', () => {
  const requests: Request[] = [];
  beforeEach(() => {
    requests.length = 0;
    vi.stubEnv('NOTTE_SDK_DISABLE_VERSION_CHECK', '1');
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
      requests.push(request.clone());
      const initializing = request.method === 'GET' && new URL(request.url).search === '';
      return Response.json(initializing ? { credentials: [] } : { detail: 'server validation' }, {
        status: initializing ? 200 : 422,
      });
    }));
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks(); });

  it.each(['add', 'get', 'delete'] as const)('sends invalid %s input and maps the API 422', async method => {
    const client = new NotteClient({ apiKey: 'synthetic-key', baseUrl: 'https://api.example.test' }); // pragma: allowlist secret
    const vault = client.Vault({ vault_id: 'owned' });
    const url = 'https://';
    const credentials = { username: 'ada', email: 'ada@example.test', password: 'synthetic', mfa_secret: '999777' }; // pragma: allowlist secret
    const pending = method === 'add' ? vault.addCredentials(url, credentials)
      : method === 'get' ? vault.getCredentials(url) : vault.deleteCredentials(url);
    await expect(pending).rejects.toBeInstanceOf(NotteAPIError);
    await expect(pending).rejects.toMatchObject({ statusCode: 422 });
    expect(requests).toHaveLength(2);
    const sent = requests[1]!;
    expect(sent.method).toBe({ add: 'POST', get: 'GET', delete: 'DELETE' }[method]);
    expect(new URL(sent.url).pathname).toBe('/vaults/owned/credentials');
    if (method === 'add') expect(await sent.json()).toEqual({ url, credentials });
    else expect(new URL(sent.url).searchParams.get('url')).toBe(url);
  });
});
