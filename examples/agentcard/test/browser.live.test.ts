import assert from 'node:assert/strict';
import { test, mock } from 'node:test';
import { Agentcard } from '@agent-cards/sdk';
import { NotteClient, sessionStatus } from 'notte-sdk';
import { runCheckout } from '../src/main.ts';

test('real Agentcard SDK attaches to Notte without payments', { skip: process.env.NOTTE_AGENTCARD_LIVE !== '1', timeout: 240_000 }, async t => {
  assert.ok(process.env.NOTTE_API_URL, 'Choose the test API explicitly');
  async function owned(fail: boolean) {
    const original = globalThis.fetch;
    const ids: string[] = [];
    let vendorCalls = 0;
    let merchantActionsStarted = false;
    globalThis.fetch = async (input, options) => {
      const url = new URL(input instanceof Request ? input.url : String(input));
      if (url.hostname.endsWith('agentcard.sh')) { vendorCalls++; throw new Error('Vendor access is disabled in this test'); }
      const response = await original(input, options);
      if (url.pathname === '/sessions/start' && response.ok) ids.push((await response.clone().json()).session_id);
      return response;
    };
    const vault = new Agentcard({
      clientId: 'offline-contract-client', clientSecret: 'offline-contract-secret', sandbox: true,
      fetchImpl: async () => { vendorCalls++; throw new Error('Vendor access is disabled in this test'); },
    });
    const refresh = mock.method(vault, 'syncRegistry', async () => {});
    try {
      const checkout = runCheckout({
        vault, userId: 'offline-user', merchant: 'example.com', amount: 100, currency: 'usd',
        onApprovalUrl: () => { throw new Error('This test must never initiate approval'); },
        purchase: async page => {
          merchantActionsStarted = true;
          await page.goto('https://example.com', { waitUntil: 'domcontentloaded', timeout: 30_000 });
          assert.equal(await page.title(), 'Example Domain');
          if (fail) await page.locator('[').click();
        },
        readMerchantOrder: async () => ({ status: 'unknown' }),
      });
      if (fail) {
        await assert.rejects(checkout, /Hosted checkout failed/);
        assert.ok(merchantActionsStarted, 'The intended browser command must actually run');
      }
      else {
        const result = await checkout;
        assert.ok(merchantActionsStarted);
        assert.notEqual(result.status, 'completed', 'No payment or merchant order exists');
        assert.equal(result.order_id, undefined);
      }
    } finally {
      refresh.mock.restore();
      globalThis.fetch = original;
      assert.equal(ids.length, 1, 'Expected one owned browser');
      const client = new NotteClient();
      let closed = false;
      for (let attempt = 0; attempt < 30; attempt++) {
        const result = await sessionStatus({ client: client.getClient(), path: { session_id: ids[0] }, throwOnError: true, signal: AbortSignal.timeout(15_000) });
        if (result.data.status === 'closed') { closed = true; break; }
        await new Promise(resolve => setTimeout(resolve, 500));
      }
      assert.ok(closed, 'Owned browser did not close');
      assert.equal(vendorCalls, 0, 'No vendor calls or payments are authorized');
    }
  }
  await t.test('real SDK attachment and unknown merchant result', () => owned(false));
  await t.test('genuine browser command failure and cleanup', () => owned(true));
});
