import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Agentcard, attachToPlaywright, CheckoutState } from '@agent-cards/sdk';
import type { NotteClient } from 'notte-sdk';
import type { chromium } from 'playwright-core';
import { runCheckout, type CheckoutOptions } from '../src/main.ts';

function fixture(outcome: 'completed' | 'unknown' = 'completed', fail?: 'attach' | 'purchase') {
  const calls: string[] = [];
  const page = { close: async () => { calls.push('page close'); } };
  const options: CheckoutOptions = {
    vault: { syncRegistry: async () => { calls.push('registry'); } } as unknown as Agentcard,
    userId: 'sandbox-user', merchant: 'sandbox.example', amount: 1200, currency: 'usd',
    onApprovalUrl: url => { assert.equal(url, 'private-test-capability'); calls.push('private delivery'); },
    purchase: async candidate => {
      assert.equal(candidate, page); calls.push('purchase');
      if (fail === 'purchase') throw new Error('sensitive transport and approval details');
    },
    readMerchantOrder: async candidate => {
      assert.equal(candidate, page); calls.push('merchant read');
      return outcome === 'completed' ? { status: 'completed', orderId: 'sandbox-order' } : { status: 'unknown' };
    },
  };
  const client = {
    Session: () => ({ use: async (run: (session: unknown) => Promise<unknown>) => {
      calls.push('owner start');
      try { return await run({ cdpUrl: async () => 'wss://private.invalid', getId: () => 'owned-session' }); }
      catch (error) {
        assert.equal((error as Error).message, 'Hosted checkout failed; verify the merchant outcome before attempting another payment', 'Sanitize before the session owner can log the error');
        throw error;
      }
      finally { calls.push('owner stop'); }
    } }),
  } as unknown as NotteClient;
  const connect = (async () => ({
    contexts: () => [{ newPage: async () => { calls.push('owned context'); return page; } }],
    close: async () => { calls.push('browser close'); },
  })) as unknown as typeof chromium.connectOverCDP;
  const attach = (async (candidate: unknown, settings: Parameters<typeof attachToPlaywright>[1]) => {
    assert.equal(candidate, page);
    assert.equal(settings.vault, options.vault);
    assert.equal(settings.user, options.userId);
    assert.equal(settings.requireMerchantResult, true);
    assert.equal(settings.merchant, options.merchant);
    assert.equal(settings.amount, options.amount);
    assert.equal(settings.currency, options.currency);
    calls.push('attach');
    if (fail === 'attach') throw new Error('sensitive transport and approval details');
    settings.onApprovalUrl!('private-test-capability');
    return {
      cancel: () => { calls.push('cancel'); },
      reconcile: async () => {
        const result = await settings.resolveMerchantResult!({ status: 'awaiting_merchant', authorizationId: 'test' });
        return { status: result.status === 'unknown' ? 'outcome_unknown' : result.status, orderId: 'orderId' in result ? result.orderId : undefined } as CheckoutState;
      },
    };
  }) as typeof attachToPlaywright;
  return { calls, options, runtime: { client, connect, attach } };
}

test('attaches before merchant actions and requires merchant evidence', async () => {
  const { calls, options, runtime } = fixture();
  assert.deepEqual(await runCheckout(options, runtime), { status: 'completed', order_id: 'sandbox-order', session_id: 'owned-session' });
  assert.deepEqual(calls, ['registry', 'owner start', 'owned context', 'attach', 'private delivery', 'purchase', 'merchant read', 'cancel', 'page close', 'browser close', 'owner stop']);
});

test('unknown outcome stays unknown without another purchase attempt', async () => {
  const { calls, options, runtime } = fixture('unknown');
  const result = await runCheckout(options, runtime);
  assert.equal(result.status, 'outcome_unknown');
  assert.equal(result.order_id, undefined);
  assert.equal(calls.filter(call => call === 'purchase').length, 1);
  assert.deepEqual(calls.slice(-3), ['page close', 'browser close', 'owner stop']);
});

for (const failure of ['attach', 'purchase'] as const) {
  test(`${failure} failure closes every owned resource and hides sensitive details`, async () => {
    const { calls, options, runtime } = fixture('completed', failure);
    await assert.rejects(runCheckout(options, runtime), { message: 'Hosted checkout failed; verify the merchant outcome before attempting another payment' });
    assert.deepEqual(calls.slice(-3), ['page close', 'browser close', 'owner stop']);
    assert.ok(!calls.includes('merchant read'));
  });
}
