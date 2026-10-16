import { afterEach, describe, expect, expectTypeOf, it, vi } from 'vitest';
import { createClient, retry, retryWebhookDelivery, type WaitAction, type WaitActionOutput } from '@/index';
import { DEFAULT_ALLOWED_PATTERNS } from '@/proxy/patterns';

afterEach(() => vi.unstubAllGlobals());

describe('generated public export compatibility', () => {
  it('preserves the existing WaitAction import', () => {
    expectTypeOf<WaitAction>().toEqualTypeOf<WaitActionOutput>();
    const action: WaitAction = { type: 'wait', time_ms: 10 };
    expect(action.time_ms).toBe(10);
  });

  it('keeps the retry helper separate from webhook delivery retry', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{"status":"queued"}', {
      status: 202, headers: { 'content-type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetch);
    expect(await retry(async () => 'helper result', { maxTries: 1 })()).toBe('helper result');
    expect(fetch).not.toHaveBeenCalled();

    const response = await retryWebhookDelivery({
      client: createClient({ baseUrl: 'https://api.test' }),
      path: { delivery_id: 'delivery-1' },
      body: { force: true, tags: ['fixture'] },
      throwOnError: true,
    });
    const request = fetch.mock.calls[0][0] as Request;
    expect(request.method).toBe('POST');
    expect(request.url).toBe('https://api.test/data/webhooks/deliveries/delivery-1/retry');
    expect(await request.json()).toEqual({ force: true, tags: ['fixture'] });
    expect(response.data).toEqual({ status: 'queued' });
  });

  it('allows the generated Data API routes without allowing unrelated paths', () => {
    for (const route of ['data/brand/retrieve', 'data/monitors/monitor-1', 'data/webhooks/deliveries/delivery-1/retry']) {
      expect(DEFAULT_ALLOWED_PATTERNS.some(pattern => pattern.test(route))).toBe(true);
    }
    expect(DEFAULT_ALLOWED_PATTERNS.some(pattern => pattern.test('data/unlisted/operation'))).toBe(false);
  });
});
