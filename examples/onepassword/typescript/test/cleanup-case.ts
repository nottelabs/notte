import assert from 'node:assert/strict';
import { mock } from 'node:test';
import { chromium } from 'playwright-core';
import { runDemo } from '../src/demo.ts';

const mode = process.argv[2];
const api = (process.env.NOTTE_API_URL || 'https://api.notte.cc').replace(/\/$/, '');
const ids: string[] = [];
const original = globalThis.fetch;
const connect = chromium.connectOverCDP.bind(chromium);
let closes = 0;
let release!: () => void;
const gate = new Promise<void>(resolve => { release = resolve; });
mock.method(chromium, 'connectOverCDP', async (endpoint: string) => {
  const browser = await connect(endpoint), close = browser.close.bind(browser);
  browser.close = async () => {
    await close();
    closes++;
    if (mode === 'timeout') await gate;
    throw new Error('PRIVATE_CLOSE_CREDENTIAL');
  };
  return browser;
});
globalThis.fetch = async (input, init) => {
  const response = await original(input, init);
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
  if (new URL(url).pathname.endsWith('/sessions/start') && response.ok) ids.push((await response.clone().json()).session_id);
  return response;
};
const status = async (id: string) => {
  const response = await original(`${api}/sessions/${id}`, {
    headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` }, signal: AbortSignal.timeout(15_000),
  });
  assert.equal(response.status, 200);
  return (await response.json() as { status: string }).status;
};
let timer: ReturnType<typeof setTimeout> | undefined;
const operation = runDemo().then(() => undefined, error => error as Error);
try {
  const failure = await Promise.race([
    operation,
    new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('Recipe exceeded its cleanup deadline')), 20_000); }),
  ]);
  assert.equal(ids.length, 1);
  assert.equal(closes, 1);
  const closed = await status(ids[0]) === 'closed';
  console.log(JSON.stringify({ session_id: ids[0], closed_before_compensation: closed }));
  assert.equal(closed, true, 'The recipe did not stop its browser');
  assert.ok(failure instanceof Error && failure.message.startsWith('Vault form failed: resolve and fill login'));
  assert.ok(!failure.message.includes('PRIVATE_'));
  console.log(JSON.stringify({ session_id: ids[0], mode, closed: true }));
} finally {
  clearTimeout(timer);
  release();
  await operation;
  globalThis.fetch = original;
  for (const id of ids) {
    if (await status(id) !== 'closed') {
      const response = await original(`${api}/sessions/${id}/stop`, {
        method: 'DELETE', headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` }, signal: AbortSignal.timeout(15_000),
      });
      assert.ok(response.ok); assert.equal(await status(id), 'closed');
    }
  }
  mock.restoreAll();
}
