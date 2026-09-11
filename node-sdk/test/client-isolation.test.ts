import { afterEach, expect, it, vi } from 'vitest';
import { NotteClient } from '@/client';
import { createClient } from '@/index';

afterEach(() => vi.unstubAllGlobals());

it.each(['http://remote.example', 'ftp://remote.example'])('rejects insecure remote API URL %s', baseUrl => {
  expect(() => new NotteClient({ baseUrl, apiKey: 'test-key' })).toThrow('HTTPS'); // pragma: allowlist secret
});

it('does not overwrite resolved defaults with explicit undefined options', () => {
  vi.stubEnv('NOTTE_API_KEY', 'environment-test-key'); // pragma: allowlist secret
  vi.stubEnv('NOTTE_API_URL', 'https://environment.example');
  try {
    const client = new NotteClient({ apiKey: undefined, baseUrl: undefined });
    expect(client.getConfig()).toEqual({ apiKey: 'environment-test-key', baseUrl: 'https://environment.example' }); // pragma: allowlist secret
  } finally { vi.unstubAllEnvs(); }
});

it('keeps client endpoints, credentials, and interceptors isolated', async () => {
  const requests: Request[] = [];
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    requests.push(request);
    return Response.json({ ok: true });
  }));
  const first = new NotteClient({ baseUrl: 'https://first.example', apiKey: 'first-test-key' }); // pragma: allowlist secret
  const second = new NotteClient({ baseUrl: 'https://second.example', apiKey: 'second-test-key' }); // pragma: allowlist secret
  expect(first.getClient()).not.toBe(second.getClient());
  await Promise.all([first.getClient().get({ url: '/probe' }), second.getClient().get({ url: '/probe' })]);
  expect(requests.map(r => [r.url, r.headers.get('authorization')])).toEqual([
    ['https://first.example/probe', 'Bearer first-test-key'],
    ['https://second.example/probe', 'Bearer second-test-key'],
  ]);
});

it('isolates legacy createClient calls as well', async () => {
  const requests: Request[] = [];
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    requests.push(request);
    return Response.json({ ok: true });
  }));
  const first = createClient({ baseUrl: 'https://first.example', token: 'first-test-token' }); // pragma: allowlist secret
  const second = createClient({ baseUrl: 'https://second.example', token: 'second-test-token' }); // pragma: allowlist secret
  expect(first).not.toBe(second);
  await Promise.all([first.get({ url: '/probe' }), second.get({ url: '/probe' })]);
  expect(requests.map(r => [r.url, r.headers.get('authorization')])).toEqual([
    ['https://first.example/probe', 'Bearer first-test-token'],
    ['https://second.example/probe', 'Bearer second-test-token'],
  ]);
});
