import assert from 'node:assert/strict';
import { test } from 'node:test';
import { NotteClient, sessionStatus } from 'notte-sdk';
import { main, withBrowser } from '../src/main.ts';

async function closed(browserId: string) {
  const client = new NotteClient();
  for (let attempt = 0; attempt < 30; attempt++) {
    const result = await sessionStatus({ client: client.getClient(), path: { session_id: browserId }, throwOnError: true, signal: AbortSignal.timeout(15_000) });
    if (result.data.status === 'closed') return;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  assert.fail('Owned browser did not close');
}

test('real Notte MCP browser protocol', { skip: process.env.NOTTE_SANDBOXES_LIVE !== '1', timeout: 180_000 }, async t => {
  assert.ok(process.env.NOTTE_API_URL, 'Choose the test API explicitly');
  await t.test('original demo navigates, observes and stops its browser', async () => {
    const result = await main();
    try { assert.equal(result.title, 'Example Domain'); }
    finally { await closed(result.browser_id); }
  });
  await t.test('genuine invalid-selector command failure still stops its browser', async () => {
    let id: string | undefined;
    try {
      await assert.rejects(withBrowser(async (call, browserId) => {
        id = browserId;
        await call('browser_action', { browser_id: browserId, action: { type: 'goto', url: 'https://example.com' } });
        await call('browser_action', { browser_id: browserId, action: { type: 'click', selector: '[' } });
      }), { message: 'Notte MCP browser task failed' });
    } finally {
      assert.ok(id, 'Expected an owned browser before the failing command');
      await closed(id);
    }
  });
});
