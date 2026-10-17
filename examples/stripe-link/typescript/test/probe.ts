import assert from 'node:assert/strict';
import { appendFileSync, readFileSync } from 'node:fs';
import Link from '@stripe/link-sdk';
import { mock } from 'node:test';
import { chromium } from 'playwright-core';
import { runDemo } from '../src/demo.ts';

const fixture = JSON.parse(readFileSync(new URL('../../test-card.json', import.meta.url), 'utf8'));
const mode = process.argv[2] ?? 'fixture';
const reject = mode.startsWith('reject');
const closing = mode === 'reject-close' || mode === 'reject-timeout';
const originalFetch = globalThis.fetch;
let closes = 0;
const keepAlive = closing ? setInterval(() => {}, 1000) : undefined;
globalThis.fetch = async (input, init) => {
    const response = await originalFetch(input, init);
    const url = new URL(input instanceof Request ? input.url : String(input));
    if (url.pathname.endsWith('/sessions/start') && response.ok) {
      const event = JSON.stringify({ session_id: (await response.clone().json()).session_id, event: 'owned' });
      console.log(event);
      if (process.env.LINK_OWNERSHIP_JOURNAL) {
        try { appendFileSync(process.env.LINK_OWNERSHIP_JOURNAL, event + '\n', { mode: 0o600, flush: true }); }
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
      if (mode === 'reject-timeout') await new Promise(() => {});
      throw new Error('PRIVATE_CLOSE_FIXTURE');
    };
    return browser;
  });
}
let calls = 0;
const fetchMock: typeof fetch = async (input, options) => {
  assert.equal(options?.method, 'GET');
  assert.equal(new URL(String(input)).searchParams.get('include'), 'card');
  calls++;
  return reject ? Response.json({ error: { message: 'PRIVATE_FIXTURE_BODY' } }, { status: 401 }) : Response.json(fixture);
};
runDemo(new Link({ accessToken: 'test-link-token', fetch: fetchMock })).then(result => {
  assert.equal(calls, 1);
  console.log(JSON.stringify(result));
}).catch(error => {
  console.error(error.message);
  process.exitCode = 1;
}).finally(() => {
  clearInterval(keepAlive);
  globalThis.fetch = originalFetch;
  mock.restoreAll();
  if (closing) assert.equal(closes, 1, 'The disconnect failure was not exercised');
});
