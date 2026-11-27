import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NotteClient, DEFAULT_NOTTE_API_URL, EU_NOTTE_API_URL, createClient, defaultApiUrl } from '@/index';
import { handleProxyRequest } from '@/proxy/core';

const EU_KEYS = [
  'sk-notte-eu-0123456789abcdef', // pragma: allowlist secret
  'sk-notte-org-eu-0123456789abcdef', // pragma: allowlist secret
  'nat_eu_0123456789abcdef', // pragma: allowlist secret
];
const DEFAULT_KEYS = [
  'sk-notte-0123456789abcdef', // pragma: allowlist secret
  'sk-notte-org-0123456789abcdef', // pragma: allowlist secret
  'nat_0123456789abcdef', // pragma: allowlist secret
  'sk-notte-europe0123456789', // pragma: allowlist secret
  'sk-notte-org-europe0123456789', // pragma: allowlist secret
  'nat_europe_0123456789', // pragma: allowlist secret
  'nat_eu0123456789', // pragma: allowlist secret
  'sk-notte-us-eu-0123456789', // pragma: allowlist secret
  'SK-NOTTE-EU-0123456789', // pragma: allowlist secret
  'test-api-key', // pragma: allowlist secret
];

function urlWarnings(warn: ReturnType<typeof vi.spyOn>): unknown[][] {
  return warn.mock.calls.filter((call: unknown[]) => String(call[0]).includes('NOTTE_API_URL is set to'));
}

beforeEach(() => {
  vi.stubEnv('NOTTE_SDK_DISABLE_VERSION_CHECK', '1');
  vi.stubEnv('NOTTE_API_URL', '');
  vi.stubEnv('NOTTE_API_KEY', '');
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('defaultApiUrl', () => {
  it('keeps the exported default unchanged', () => {
    expect(DEFAULT_NOTTE_API_URL).toBe('https://api.notte.cc');
    expect(EU_NOTTE_API_URL).toBe('https://eu-api.notte.cc');
  });

  it.each(EU_KEYS)('uses the EU API for %s', (key) => {
    expect(defaultApiUrl(key)).toBe(EU_NOTTE_API_URL);
  });

  it.each(DEFAULT_KEYS)('uses the default API for %s', (key) => {
    expect(defaultApiUrl(key)).toBe(DEFAULT_NOTTE_API_URL);
  });

  it('uses the default API without a credential', () => {
    expect(defaultApiUrl()).toBe(DEFAULT_NOTTE_API_URL);
    expect(defaultApiUrl(null)).toBe(DEFAULT_NOTTE_API_URL);
    expect(defaultApiUrl('')).toBe(DEFAULT_NOTTE_API_URL);
  });
});

describe('NotteClient base URL', () => {
  it.each(EU_KEYS)('sends %s to the EU API without a warning', async (apiKey) => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const requests: Request[] = [];
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
      requests.push(request);
      return Response.json({ ok: true });
    }));
    const client = new NotteClient({ apiKey });
    expect(client.getConfig().baseUrl).toBe(EU_NOTTE_API_URL);
    await client.getClient().get({ url: '/probe' });
    expect(requests.map((request) => request.url)).toEqual(['https://eu-api.notte.cc/probe']);
    expect(urlWarnings(warn)).toEqual([]);
  });

  it.each(DEFAULT_KEYS)('keeps %s on the default API without a warning', (apiKey) => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    expect(new NotteClient({ apiKey }).getConfig().baseUrl).toBe(DEFAULT_NOTTE_API_URL);
    expect(urlWarnings(warn)).toEqual([]);
  });

  it('reads the region of NOTTE_API_KEY', () => {
    vi.stubEnv('NOTTE_API_KEY', EU_KEYS[1]);
    expect(new NotteClient().getConfig().baseUrl).toBe(EU_NOTTE_API_URL);
  });

  it.each([EU_KEYS[0], DEFAULT_KEYS[0]])('lets an explicit baseUrl win over %s', (apiKey) => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    expect(new NotteClient({ apiKey, baseUrl: 'https://custom.example' }).getConfig().baseUrl).toBe('https://custom.example');
    expect(urlWarnings(warn)).toHaveLength(1);
  });

  it.each([EU_KEYS[0], DEFAULT_KEYS[0]])('lets NOTTE_API_URL win over %s', (apiKey) => {
    vi.stubEnv('NOTTE_API_URL', 'https://us-staging.notte.cc');
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    expect(new NotteClient({ apiKey }).getConfig().baseUrl).toBe('https://us-staging.notte.cc');
    expect(urlWarnings(warn)).toHaveLength(1);
  });

  it('still warns when an EU key is pointed at the default API', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    expect(new NotteClient({ apiKey: EU_KEYS[0], baseUrl: DEFAULT_NOTTE_API_URL }).getConfig().baseUrl).toBe(DEFAULT_NOTTE_API_URL);
    expect(urlWarnings(warn)).toHaveLength(1);
  });
});

describe('legacy createClient base URL', () => {
  it.each([
    [EU_KEYS[2], 'https://eu-api.notte.cc/probe'],
    [DEFAULT_KEYS[0], 'https://api.notte.cc/probe'],
  ])('follows the region of token %s', async (token, expected) => {
    const requests: Request[] = [];
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
      requests.push(request);
      return Response.json({ ok: true });
    }));
    await createClient({ token }).get({ url: '/probe' });
    expect(requests.map((request) => request.url)).toEqual([expected]);
  });

  it('lets an explicit baseUrl win', async () => {
    const requests: Request[] = [];
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
      requests.push(request);
      return Response.json({ ok: true });
    }));
    await createClient({ token: EU_KEYS[0], baseUrl: 'https://custom.example' }).get({ url: '/probe' });
    expect(requests.map((request) => request.url)).toEqual(['https://custom.example/probe']);
  });
});

describe('proxy base URL', () => {
  async function forwardedUrl(apiKey: string, apiUrl?: string): Promise<string> {
    const fetch = vi.fn(async () => Response.json({ ok: true }));
    vi.stubGlobal('fetch', fetch);
    const request = new Request('http://localhost:3000/api/notte/sessions');
    await handleProxyRequest(request, ['sessions'], { authenticate: async () => apiKey, apiUrl });
    expect(fetch).toHaveBeenCalledTimes(1);
    return String((fetch.mock.calls[0] as unknown[])[0]);
  }

  it.each(EU_KEYS)('forwards %s to the EU API', async (apiKey) => {
    expect(await forwardedUrl(apiKey)).toBe('https://eu-api.notte.cc/sessions');
  });

  it.each(DEFAULT_KEYS)('forwards %s to the default API', async (apiKey) => {
    expect(await forwardedUrl(apiKey)).toBe('https://api.notte.cc/sessions');
  });

  it('lets a configured apiUrl win', async () => {
    expect(await forwardedUrl(EU_KEYS[0], 'https://custom.example/')).toBe('https://custom.example/sessions');
  });
});
