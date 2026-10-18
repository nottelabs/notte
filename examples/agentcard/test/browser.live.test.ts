import assert from 'node:assert/strict';
import { appendFileSync } from 'node:fs';
import { inspect } from 'node:util';
import { test, mock } from 'node:test';
import { Agentcard } from '@agent-cards/sdk';
import { NotteClient, sessionStatus } from 'notte-sdk';
import { chromium, type Browser } from 'playwright-core';
import { runCheckout } from '../src/main.ts';

async function assertClosed(client: NotteClient, id: string) {
  for (let attempt = 0; attempt < 30; attempt++) {
    const result = await sessionStatus({ client: client.getClient(), path: { session_id: id }, throwOnError: true, signal: AbortSignal.timeout(15_000) });
    if (result.data.status === 'closed') {
      if (process.env.AGENTCARD_OWNERSHIP_JOURNAL) appendFileSync(process.env.AGENTCARD_OWNERSHIP_JOURNAL, JSON.stringify({ event: 'closed', session_id: id }) + '\n', { mode: 0o600 });
      return;
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error('Owned browser did not close');
}

test('real Agentcard SDK attaches to Notte without payments', { skip: process.env.NOTTE_AGENTCARD_LIVE !== '1', timeout: 360_000 }, async t => {
  assert.ok(process.env.NOTTE_API_URL, 'Choose the test API explicitly');
  async function owned(mode: 'success' | 'failure' | 'page-reject' | 'page-timeout' | 'browser-reject' | 'browser-timeout' | 'reconciled-page-reject' | 'reconciled-browser-timeout' | 'reconciled-stop-reject') {
    const client = new NotteClient();
    let id: string | undefined;
    let vendorCalls = 0;
    let merchantActionsStarted = false;
    let closeFaultReached = false;
    let nativeBrowser: Browser | undefined;
    let failure: unknown;
    let result: Awaited<ReturnType<typeof runCheckout>> | undefined;
    const restores: (() => void)[] = [];
    const messages: string[] = [];
    const factory = client.Session.bind(client);
    const fault = mode.replace(/^reconciled-/, '');
    const succeeds = mode === 'success' || mode.startsWith('reconciled-');
    const owner = mock.method(client, 'Session', (...args: Parameters<typeof factory>) => {
      const session = factory(...args);
      if (fault === 'stop-reject') {
        const stop = session.stop.bind(session);
        const stopping = mock.method(session, 'stop', async (...args: Parameters<typeof stop>) => {
          await stop(...args);
          closeFaultReached = true;
          throw new Error('private-close-body-fixture');
        });
        restores.push(() => stopping.mock.restore());
      }
      const start = session.start.bind(session);
      const starting = mock.method(session, 'start', async (...options: Parameters<typeof start>) => {
        const response = await start(...options);
        id = session.getId() ?? undefined;
        if (process.env.AGENTCARD_OWNERSHIP_JOURNAL) appendFileSync(process.env.AGENTCARD_OWNERSHIP_JOURNAL, JSON.stringify({ event: 'allocated', session_id: id }) + '\n', { mode: 0o600 });
        return response;
      });
      restores.push(() => starting.mock.restore());
      return session;
    });
    const vault = new Agentcard({
      clientId: 'offline-contract-client', clientSecret: 'offline-contract-secret', sandbox: true, // pragma: allowlist secret
      fetchImpl: async () => { vendorCalls++; throw new Error('Vendor access is disabled in this test'); },
    });
    const refresh = mock.method(vault, 'syncRegistry', async () => {});
    const warning = mock.method(console, 'warn', (...args: unknown[]) => { messages.push(inspect(args)); });
    const connect = (async (endpointURL: string) => {
      nativeBrowser = await chromium.connectOverCDP(endpointURL);
      if (fault.startsWith('browser-')) {
        const closing = mock.method(nativeBrowser, 'close', async () => {
          closeFaultReached = true;
          if (fault.endsWith('timeout')) await new Promise<void>(() => {});
          throw new Error('private-close-body-fixture');
        });
        restores.push(() => closing.mock.restore());
      }
      if (fault.startsWith('page-')) {
        const context = nativeBrowser.contexts()[0];
        const newPage = context.newPage.bind(context);
        const creating = mock.method(context, 'newPage', async () => {
          const page = await newPage();
          const closing = mock.method(page, 'close', async () => {
            closeFaultReached = true;
            if (fault.endsWith('timeout')) await new Promise<void>(() => {});
            throw new Error('private-close-body-fixture');
          });
          restores.push(() => closing.mock.restore());
          return page;
        });
        restores.push(() => creating.mock.restore());
      }
      return nativeBrowser;
    }) as typeof chromium.connectOverCDP;
    try {
      try {
        result = await runCheckout({
          vault, userId: 'offline-user', merchant: 'example.com', amount: 100, currency: 'usd',
          onApprovalUrl: () => { throw new Error('This test must never initiate approval'); },
          purchase: async page => {
            merchantActionsStarted = true;
            await page.goto('https://example.com', { waitUntil: 'domcontentloaded', timeout: 30_000 });
            assert.equal(await page.title(), 'Example Domain');
            if (!succeeds) await page.locator('[private-merchant-body-fixture').click();
          },
          readMerchantOrder: async () => ({ status: 'unknown' }),
        }, { client, connect });
      } catch (error) { failure = error; }
    } finally {
      try {
        if (id) {
          let closed = false;
          try { await assertClosed(client, id); closed = true; }
          finally {
            if (!closed) {
              const response = await fetch(`${process.env.NOTTE_API_URL}/sessions/${id}/stop`, {
                method: 'DELETE', headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` },
                signal: AbortSignal.timeout(15_000), redirect: 'error',
              });
              assert.ok(response.ok, 'Fallback stop failed for the owned browser');
              await assertClosed(client, id);
            }
          }
        }
      } finally {
        for (const restore of restores.reverse()) restore();
        refresh.mock.restore();
        owner.mock.restore();
        warning.mock.restore();
        if (nativeBrowser) {
          let timer: ReturnType<typeof setTimeout> | undefined;
          try { await Promise.race([nativeBrowser.close(), new Promise<void>(resolve => { timer = setTimeout(resolve, 5_000); })]); }
          finally { clearTimeout(timer); }
        }
      }
    }
    assert.ok(id, 'Expected one owned browser');
    assert.ok(merchantActionsStarted, 'The intended browser command must actually run');
    assert.equal(vendorCalls, 0, 'No vendor calls or payments are authorized');
    if (fault.startsWith('page-') || fault.startsWith('browser-') || fault === 'stop-reject') assert.ok(closeFaultReached, 'The native close fault must actually run');
    if (succeeds) {
      assert.ifError(failure);
      assert.ok(result);
      assert.notEqual(result.status, 'completed', 'No payment or merchant order exists');
      assert.equal(result.order_id, undefined);
      assert.equal(result.session_id, id);
      if (mode.startsWith('reconciled-')) {
        const stage = fault.startsWith('page-') ? 'page_close' : fault.startsWith('browser-') ? 'browser_close' : 'session_stop';
        assert.deepEqual(result.cleanup_errors, [stage]);
      } else assert.equal(result.cleanup_errors, undefined);
      assert.doesNotMatch(inspect(result) + messages.join('\n'), /private-(merchant|close)-body-fixture/);
    } else {
      assert.ok(failure instanceof Error);
      assert.equal(failure.message, 'Hosted checkout failed; verify the merchant outcome before attempting another payment');
      assert.equal(failure.cause, undefined);
      assert.doesNotMatch(inspect(failure) + failure.stack + messages.join('\n'), /private-(merchant|close)-body-fixture/);
    }
  }
  for (const mode of ['success', 'failure', 'page-reject', 'page-timeout', 'browser-reject', 'browser-timeout', 'reconciled-page-reject', 'reconciled-browser-timeout', 'reconciled-stop-reject'] as const) {
    await t.test(mode, () => owned(mode));
  }
});
