import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NotteClient } from '@/client';
import { NotteAPIError } from '@/errors';
import type { FileListOptions } from '@/files';

describe('file request parity', () => {
  const requests: Request[] = [];
  beforeEach(() => {
    requests.length = 0;
    vi.stubEnv('NOTTE_SDK_DISABLE_VERSION_CHECK', '1');
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
      requests.push(request.clone());
      return Response.json({ detail: 'invalid file request' }, { status: 422 });
    }));
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks(); });

  it('sends invalid list filters and preserves encoded path segments and typed errors', async () => {
    const client = new NotteClient({ apiKey: 'synthetic-key', baseUrl: 'https://api.example.test' }); // pragma: allowlist secret
    const pending = client.Files('a/b ?#%é').list({ source: 'invalid', limit: 0, offset: -1 } as unknown as FileListOptions);
    await expect(pending).rejects.toBeInstanceOf(NotteAPIError);
    await expect(pending).rejects.toMatchObject({ statusCode: 422 });
    expect(requests).toHaveLength(1);
    const url = new URL(requests[0]!.url);
    expect(url.pathname).toBe('/sessions/a%2Fb%20%3F%23%25%C3%A9/files');
    expect(Object.fromEntries(url.searchParams)).toEqual({ source: 'invalid', limit: '0', offset: '-1' });
  });
});
