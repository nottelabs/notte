import assert from 'node:assert/strict';
import Lightcone from '@tzafon/lightcone';
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';
import { withBrowserDeadline } from '../src/computer.ts';
import { runDemo } from '../src/demo.ts';
import { CODE, wire } from './fixture.ts';

async function cancelledBrowser() {
  const client = new NotteClient();
  return client.Session({ max_duration_minutes: 3 }).use(async session => {
    const id = session.getId()!;
    try {
      const browser = await chromium.connectOverCDP(await session.cdpUrl());
      const page = browser.contexts()[0].pages()[0];
      const controller = new AbortController();
      const pending = withBrowserDeadline(browser, controller.signal, () => page.locator('#never-present').waitFor({ timeout: 0 }));
      const started = Date.now();
      const timer = setTimeout(() => controller.abort(), 50);
      try { await assert.rejects(pending); }
      finally { clearTimeout(timer); }
      assert.ok(Date.now() - started < 10_000, 'Browser cancellation did not disconnect promptly');
      return { cancelled: true, session_id: id };
    } catch { throw new Error(`Lightcone form failed: cancellation probe (session ${id})`); }
  });
}

const { mock, requests } = wire(process.argv[2], true);
const operation = process.argv[2] === 'cancel' ? cancelledBrowser() : runDemo(new Lightcone({ apiKey: 'fixture-provider-key', baseURL: 'https://lightcone.invalid', fetch: mock, maxRetries: 0 }), CODE); // pragma: allowlist secret
operation.then(result => {
  if (process.argv[2] !== 'cancel') assert.equal(requests.length, 3);
  console.log(JSON.stringify(result));
}).catch(error => {
  if (process.argv[2] !== 'cancel') assert.equal(requests.length, 1);
  console.error(error.message);
  process.exitCode = 1;
});
