import assert from 'node:assert/strict';
import { writeFileSync } from 'node:fs';
import { mock } from 'node:test';
import { chromium } from 'playwright-core';
import { capturePage } from '../src/main.ts';

const mode = process.argv[2];
const originalFetch = globalThis.fetch, connect = chromium.connectOverCDP.bind(chromium);
const ids: string[] = [];
let closes = 0, navigations = 0;
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
  browser.close = async () => {
    await close(); closes++;
    if (mode === 'close-timeout') await new Promise(() => {});
    throw new Error('PRIVATE_BROWSER_CLOSE https://private.invalid/credential');
  };
  return browser;
});
const status = async (id: string) => {
  const response = await originalFetch(`${process.env.NOTTE_API_URL}/sessions/${id}`, {
    headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` }, signal: AbortSignal.timeout(15_000),
  });
  assert.equal(response.status, 200);
  return (await response.json() as { status: string }).status;
};
try {
  await assert.rejects(capturePage(), { message: 'Could not capture the hosted page' });
  assert.equal(ids.length, 1); assert.equal(closes, 1); assert.equal(navigations, 1);
  assert.equal(await status(ids[0]), 'closed', 'Owner did not release its browser');
  console.log(JSON.stringify({ session_id: ids[0], closed: true, mode }));
} finally {
  clearInterval(keepAlive); globalThis.fetch = originalFetch; mock.restoreAll();
  for (const id of ids) {
    if (await status(id) !== 'closed') {
      const response = await originalFetch(`${process.env.NOTTE_API_URL}/sessions/${id}/stop`, {
        method: 'DELETE', headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` }, signal: AbortSignal.timeout(15_000),
      });
      assert.ok(response.ok); assert.equal(await status(id), 'closed');
    }
  }
}
