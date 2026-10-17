import assert from 'node:assert/strict';
import { appendFileSync } from 'node:fs';
import { mock } from 'node:test';
import { chromium } from 'playwright-core';
import { runDemo } from '../src/demo.ts';
import { transport } from './transport.ts';

const mode = process.argv[2] ?? 'fixture';
const closing = mode === 'iam-reject-close' || mode === 'iam-reject-timeout';
const originalFetch = globalThis.fetch;
let closes = 0;
const keepAlive = closing ? setInterval(() => {}, 1000) : undefined;
globalThis.fetch = async (input, init) => {
  const response = await originalFetch(input, init);
  const url = new URL(input instanceof Request ? input.url : String(input));
  if (url.pathname.endsWith('/sessions/start') && response.ok) {
    const event = JSON.stringify({ event: 'owned', session_id: (await response.clone().json()).session_id });
    console.log(event);
    if (process.env.WATSONX_OWNERSHIP_JOURNAL) {
      try { appendFileSync(process.env.WATSONX_OWNERSHIP_JOURNAL, event + '\n', { mode: 0o600, flush: true }); }
      catch { console.warn('Ownership journal unavailable'); }
    }
  }
  return response;
};
if (closing) {
  const connect = chromium.connectOverCDP.bind(chromium);
  mock.method(chromium, 'connectOverCDP', async (endpoint: string) => {
    const browser = await connect(endpoint), close = browser.close.bind(browser);
    browser.close = async () => {
      await close();
      closes++;
      if (mode === 'iam-reject-timeout') await new Promise(() => {});
      throw new Error('PRIVATE_CLOSE_FIXTURE');
    };
    return browser;
  });
}
runDemo(transport(mode.startsWith('iam-reject') ? 'iam-reject' : mode, true).mock).then(result => console.log(JSON.stringify(result))).catch(error => {
  console.error(error.message);
  process.exitCode = 1;
}).finally(() => {
  clearInterval(keepAlive);
  globalThis.fetch = originalFetch;
  mock.restoreAll();
  if (closing) assert.equal(closes, 1, 'The disconnect failure was not exercised');
});
