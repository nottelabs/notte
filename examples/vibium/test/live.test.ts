import assert from 'node:assert/strict';
import { test } from 'node:test';
import { NotteClient } from 'notte-sdk';
import { withNotteVibium } from '../src/connection.ts';

const live = process.env.NOTTE_VIBIUM_LIVE === '1';
const html = `<title>Owned Vibium task</title><input id="value"><button id="copy"
onclick="document.querySelector('output').textContent=document.querySelector('input').value">Copy</button><output></output>`;
const url = `data:text/html,${encodeURIComponent(html)}`;

for (const mode of ['success', 'failure', 'cancel'] as const) {
  test(`native Vibium ${mode}, actions, and independent API closure`, { skip: !live, timeout: 240_000 }, async () => {
    const controller = new AbortController();
    const client = new NotteClient();
    let id: string | undefined;
    let actionsCompleted = false;
    try {
      const operation = withNotteVibium(async (driver, bidi, sessionId, signal) => {
        id = sessionId;
        let remote = await driver.connect(bidi, signal);
        const page = await remote.page();
        await page.go(url);
        await (await page.find('#value')).fill('native-action');
        await (await page.find('#copy')).click();
        assert.equal(await (await page.find('output')).text(), 'native-action');
        actionsCompleted = true;
        if (mode === 'cancel') {
          setTimeout(() => controller.abort(), 100);
          await page.find('#absent-owned-fixture', { timeout: 30_000 });
        }
        if (mode === 'failure') await page.find('#absent-owned-fixture', { timeout: 250 });
        const png = await page.screenshot();
        assert.ok(png.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])));
        assert.ok(png.length > 100);
        await driver.disconnect(remote);
        remote = await driver.connect(bidi, signal);
        assert.equal(await (await remote.page()).title(), 'Owned Vibium task');
        await driver.disconnect(remote);
      }, { client, signal: controller.signal });
      if (mode === 'success') await operation;
      else await assert.rejects(operation, new RegExp(`Vibium ${mode === 'cancel' ? 'cancelled' : 'failed'} \\(session [a-f0-9-]+\\)`));
      assert.ok(actionsCompleted, 'The case must execute actual native browser actions');
    } finally {
      if (id) {
        let closed = false;
        for (let attempt = 0; attempt < 40; attempt++) {
          const status = await fetch(new URL(`/sessions/${id}`, process.env.NOTTE_API_URL ?? 'https://api.notte.cc'), {
            headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY!}` }, redirect: 'error', signal: AbortSignal.timeout(5_000),
          });
          assert.ok(status.ok, 'Independent session status request failed');
          if (((await status.json()) as { status?: string }).status === 'closed') { closed = true; break; }
          await new Promise(resolve => setTimeout(resolve, 250));
        }
        assert.ok(closed, 'Independent API status must confirm the owned session closed');
      }
    }
  });
}
