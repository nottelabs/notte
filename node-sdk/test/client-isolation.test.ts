import { afterEach, expect, it, vi } from 'vitest';
import { NotteClient } from '@/client';

afterEach(() => vi.unstubAllGlobals());

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
