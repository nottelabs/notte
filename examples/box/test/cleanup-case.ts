import assert from 'node:assert/strict';
import { writeFileSync } from 'node:fs';
import { mock } from 'node:test';
import { setTimeout as sleep } from 'node:timers/promises';
import { chromium } from 'playwright-core';
import { capturePage } from '../src/main.ts';

const mode = process.argv[2];
const originalFetch = globalThis.fetch, connect = chromium.connectOverCDP.bind(chromium);
const ids: string[] = [];
const api = (process.env.NOTTE_API_URL || 'https://api.notte.cc').replace(/\/$/, '');
let closes = 0, navigations = 0, cleanupFailed = false;
let cleanupError: unknown;
let release!: () => void;
const gate = new Promise<void>(resolve => { release = resolve; });
let closeOperation: Promise<void> | undefined;
const keepAlive = setInterval(() => {}, 1000);
globalThis.fetch = async (input, init) => {
  const response = await originalFetch(input, init);
  const url = new URL(input instanceof Request ? input.url : String(input));
  if (url.pathname.endsWith('/sessions/start') && response.ok) {
    const id = (await response.clone().json()).session_id;
    ids.push(id); writeFileSync(process.env.NOTTE_BOX_TEST_JOURNAL!, id);
  }
  return response;
};
mock.method(chromium, 'connectOverCDP', async (endpoint: string) => {
  const browser = await connect(endpoint), close = browser.close.bind(browser);
  const context = browser.contexts()[0], newPage = context.newPage.bind(context);
  context.newPage = async () => {
    const page = await newPage(), goto = page.goto.bind(page);
    page.goto = async (url, options) => {
      navigations++;
      return goto(mode === 'navigation' ? 'not-a-valid-url' : url, options);
    };
    return page;
  };
  browser.close = () => {
    closeOperation = (async () => {
      closes++;
      if (mode === 'close-timeout') await gate;
      await close();
      throw new Error('PRIVATE_BROWSER_CLOSE https://private.invalid/credential');
    })();
    return closeOperation;
  };
  return browser;
});
const status = async (id: string, signal = AbortSignal.timeout(15_000)) => {
  const response = await originalFetch(`${api}/sessions/${id}`, {
    headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` }, signal,
  });
  assert.equal(response.status, 200);
  const value = (await response.json() as { status: string }).status;
  assert.ok(value === 'active' || value === 'closed', 'Unknown session status');
  return value;
};
const waitClosed = async (id: string) => {
  const signal = AbortSignal.timeout(15_000);
  while (await status(id, signal) !== 'closed') await sleep(250, undefined, { signal });
  return true;
};
try {
  await assert.rejects(capturePage(), { message: 'Could not capture the hosted page' });
  assert.equal(ids.length, 1); assert.equal(closes, 1); assert.equal(navigations, 1);
  const closed = await waitClosed(ids[0]);
  console.log(JSON.stringify({ session_id: ids[0], closed, closed_before_compensation: closed, mode }));
} finally {
  release();
  await closeOperation?.catch(() => {});
  clearInterval(keepAlive); globalThis.fetch = originalFetch;
  try {
    for (const id of ids) {
      let closed = false;
      try { closed = await status(id) === 'closed'; } catch { /* Still attempt the owned stop. */ }
      if (!closed) {
        const response = await originalFetch(`${api}/sessions/${id}/stop`, {
          method: 'DELETE', headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` }, signal: AbortSignal.timeout(15_000),
        });
        assert.ok(response.ok);
      }
      await waitClosed(id);
    }
  } catch (error) {
    cleanupFailed = true;
    cleanupError = error;
  } finally { mock.restoreAll(); }
}
if (cleanupFailed) throw cleanupError;
