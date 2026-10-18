import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Agentcard, attachToPlaywright, CheckoutState } from '@agent-cards/sdk';
import type { NotteClient } from 'notte-sdk';
import type { chromium } from 'playwright-core';
import { runCheckout, type CheckoutOptions } from '../src/main.ts';

type CleanupStage = 'checkout_cancel' | 'page_close' | 'browser_close' | 'session_stop';

function fixture(outcome: 'completed' | 'unknown' = 'completed', fail?: 'attach' | 'purchase', cleanupFailures: CleanupStage[] = [], stall?: 'page_close' | 'browser_close') {
  const calls: string[] = [];
  const close = async (stage: CleanupStage, label: string) => {
    calls.push(label);
    if (stall === stage) await new Promise<void>(() => {});
    if (cleanupFailures.includes(stage)) throw new Error('private cleanup capability');
  };
  const page = { close: () => close('page_close', 'page close') };
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
      finally { await close('session_stop', 'owner stop'); }
    } }),
  } as unknown as NotteClient;
  const connect = (async () => ({
    contexts: () => [{ newPage: async () => { calls.push('owned context'); return page; } }],
    close: () => close('browser_close', 'browser close'),
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
      cancel: () => {
        calls.push('cancel');
        if (cleanupFailures.includes('checkout_cancel')) throw new Error('private cleanup capability');
      },
      reconcile: async () => {
        const result = await settings.resolveMerchantResult!({ status: 'awaiting_merchant', authorizationId: 'test' });
        return { status: result.status === 'unknown' ? 'outcome_unknown' : result.status, orderId: 'orderId' in result ? result.orderId : undefined } as CheckoutState;
      },
    };
  }) as typeof attachToPlaywright;
  return { calls, options, runtime: { client, connect, attach } };
}

for (const outcome of ['completed', 'unknown'] as const) {
  for (const stage of ['checkout_cancel', 'page_close', 'browser_close', 'session_stop'] as const) {
    test(`${outcome} outcome survives ${stage} failure`, async () => {
      const { calls, options, runtime } = fixture(outcome, undefined, [stage]);
      const result = await runCheckout(options, runtime);
      assert.deepEqual(result, {
        status: outcome === 'completed' ? 'completed' : 'outcome_unknown',
        order_id: outcome === 'completed' ? 'sandbox-order' : undefined,
        session_id: 'owned-session', cleanup_errors: [stage],
      });
      assert.deepEqual(calls.slice(-4), ['cancel', 'page close', 'browser close', 'owner stop']);
      assert.equal(calls.filter(call => call === 'purchase').length, 1);
      assert.equal(calls.filter(call => call === 'merchant read').length, 1);
      assert.ok(!JSON.stringify(result).includes('private'));
    });
  }
}

test('all cleanup failures preserve the reconciled order and attempt every release', async () => {
  const stages: CleanupStage[] = ['checkout_cancel', 'page_close', 'browser_close', 'session_stop'];
  const { calls, options, runtime } = fixture('completed', undefined, stages);
  const result = await runCheckout(options, runtime);
  assert.equal(result.order_id, 'sandbox-order');
  assert.equal(result.session_id, 'owned-session');
  assert.deepEqual(result.cleanup_errors, stages);
  assert.deepEqual(calls.slice(-4), ['cancel', 'page close', 'browser close', 'owner stop']);
  assert.equal(calls.filter(call => call === 'purchase').length, 1);
});

test('cleanup failures cannot turn an unreconciled purchase into a result', async () => {
  const stages: CleanupStage[] = ['checkout_cancel', 'page_close', 'browser_close', 'session_stop'];
  const { calls, options, runtime } = fixture('completed', 'purchase', stages);
  await assert.rejects(runCheckout(options, runtime), {
    message: 'Hosted checkout failed; verify the merchant outcome before attempting another payment',
  });
  assert.deepEqual(calls.slice(-4), ['cancel', 'page close', 'browser close', 'owner stop']);
  assert.equal(calls.filter(call => call === 'purchase').length, 1);
  assert.ok(!calls.includes('merchant read'));
});

for (const stage of ['page_close', 'browser_close'] as const) {
  test(`reconciled order survives stalled ${stage}`, { timeout: 10_000 }, async () => {
    const { calls, options, runtime } = fixture('completed', undefined, [], stage);
    const result = await runCheckout(options, runtime);
    assert.equal(result.status, 'completed');
    assert.equal(result.order_id, 'sandbox-order');
    assert.equal(result.session_id, 'owned-session');
    assert.deepEqual(result.cleanup_errors, [stage]);
    assert.deepEqual(calls.slice(-4), ['cancel', 'page close', 'browser close', 'owner stop']);
    assert.equal(calls.filter(call => call === 'purchase').length, 1);
  });
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
