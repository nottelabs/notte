import assert from 'node:assert/strict';
import { appendFileSync } from 'node:fs';
import { mock } from 'node:test';
import Lightcone from '@tzafon/lightcone';
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';
import { withBrowserDeadline } from '../src/computer.ts';
import { runDemo } from '../src/demo.ts';
import { CODE, wire } from './fixture.ts';

const mode = process.argv[2];
const closing = ['reject-close', 'reject-timeout', 'protocol-close', 'cancel-timeout'].includes(mode);
const originalFetch = globalThis.fetch;
const keepAlive = closing ? setInterval(() => {}, 1000) : undefined;
let closes = 0;
let cleanup: (() => Promise<void>) | undefined;
globalThis.fetch = async (input, options) => {
  const response = await originalFetch(input, options);
  const url = new URL(input instanceof Request ? input.url : String(input));
  if (url.pathname.endsWith('/sessions/start') && response.ok) {
    const event = JSON.stringify({ event: 'owned', session_id: (await response.clone().json()).session_id });
    console.log(event);
    if (process.env.TZAFON_OWNERSHIP_JOURNAL) {
      try { appendFileSync(process.env.TZAFON_OWNERSHIP_JOURNAL, event + '\n', { mode: 0o600, flush: true }); }
      catch { console.warn('Ownership journal unavailable'); }
    }
  }
  return response;
};
if (closing) {
  const connect = chromium.connectOverCDP.bind(chromium);
  mock.method(chromium, 'connectOverCDP', async (...args: Parameters<typeof chromium.connectOverCDP>) => {
    const browser = await connect(...args), close = browser.close.bind(browser);
    browser.close = async () => {
      closes++;
      if (mode === 'cancel-timeout') await new Promise<void>(() => {});
      await close();
      if (mode === 'reject-timeout') await new Promise<void>(() => {});
      throw new Error('PRIVATE_CLOSE_FIXTURE');
    };
    cleanup = async () => {
      browser.close = close;
      let timer: ReturnType<typeof setTimeout> | undefined;
      try { await Promise.race([close(), new Promise<void>(resolve => { timer = setTimeout(resolve, 5000); })]); }
      finally { clearTimeout(timer); }
    };
    return browser;
  });
}

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

const { mock: fetchMock, requests } = wire(mode.startsWith('reject') ? 'reject' : mode, true);
const operation = mode.startsWith('cancel') ? cancelledBrowser() : runDemo(new Lightcone({ apiKey: 'fixture-provider-key', baseURL: 'https://lightcone.invalid', fetch: fetchMock, maxRetries: 0 }), CODE); // pragma: allowlist secret
operation.then(result => {
  if (!mode.startsWith('cancel')) assert.equal(requests.length, 3);
  console.log(JSON.stringify(result));
}).catch(error => {
  if (!mode.startsWith('cancel')) assert.equal(requests.length, mode === 'protocol-close' ? 3 : 1);
  console.error(error.message);
  process.exitCode = 1;
}).finally(async () => {
  clearInterval(keepAlive);
  globalThis.fetch = originalFetch;
  mock.restoreAll();
  if (cleanup) await cleanup();
  if (closing) assert.equal(closes, 1, 'The native disconnect fault must run once');
});
