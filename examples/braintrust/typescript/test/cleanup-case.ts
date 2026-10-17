import assert from 'node:assert/strict';
import { mock } from 'node:test';
import * as braintrust from 'braintrust';
import { chromium } from 'playwright-core';

const mode = process.argv[2];
const memory = new braintrust.TestBackgroundLogger();
const state = new braintrust.BraintrustState({ noExitFlush: true });
state.appUrl = 'https://offline.invalid';
state.orgName = 'offline';
state.setFetch(async () => { throw new Error('Unexpected vendor HTTP request'); });
state.setOverrideBgLogger(memory);
const logger = new braintrust.Logger(state, new braintrust.LazyValue(async () => ({
  org_id: '00000000-0000-4000-8000-000000000001',
  project: { id: '00000000-0000-4000-8000-000000000002', name: 'offline', fullInfo: {} },
})), { asyncFlush: true });
mock.module('braintrust', { namedExports: { initLogger: () => logger } });
const { runDemo } = await import('../src/demo.ts');
const originalFetch = globalThis.fetch, connect = chromium.connectOverCDP.bind(chromium), flush = logger.flush.bind(logger);
const ids: string[] = [];
let closes = 0, flushes = 0;
mock.method(chromium, 'connectOverCDP', async (endpoint: string) => {
  const browser = await connect(endpoint), close = browser.close.bind(browser);
  browser.close = async () => {
    await close();
    closes++;
    if (mode === 'navigation') throw new Error('PRIVATE_CLEANUP_BODY https://private.invalid/credential');
    if (mode === 'close-timeout') await new Promise(() => {});
  };
  return browser;
});
mock.method(logger, 'flush', async () => {
  await flush();
  flushes++;
  if (mode !== 'success') throw new Error('PRIVATE_FLUSH_BODY https://private.invalid/credential');
});
globalThis.fetch = async (input, init) => {
  const response = await originalFetch(input, init);
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
  if (new URL(url).pathname.endsWith('/sessions/start') && response.ok) ids.push((await response.clone().json()).session_id);
  return response;
};
const status = async (id: string) => {
  const response = await originalFetch(`${process.env.NOTTE_API_URL}/sessions/${id}`, {
    headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` }, signal: AbortSignal.timeout(15_000),
  });
  assert.equal(response.status, 200);
  return (await response.json() as { status: string }).status;
};
try {
  let result: Awaited<ReturnType<typeof runDemo>> | undefined, failure: string | undefined;
  try { result = await runDemo(mode === 'navigation' ? 'not-a-valid-url' : 'https://example.com'); }
  catch (error) { failure = error instanceof Error ? error.message : 'Unknown failure'; }
  assert.equal(ids.length, 1); assert.equal(closes, 1); assert.equal(flushes, 1);
  const closed = await status(ids[0]) === 'closed';
  console.log(JSON.stringify({ mode, session_id: ids[0], closed_before_compensation: closed,
    private_body: failure?.includes('PRIVATE_') ?? false, navigation_error_preserved: failure?.startsWith('Browser task failed: navigate') ?? false }));
  assert.equal(closed, true, 'Owner did not release its browser');
  const rows = await memory.drain(), serialized = JSON.stringify(rows);
  for (const value of [process.env.NOTTE_API_KEY!, process.env.BRAINTRUST_API_KEY!, 'PRIVATE_', 'wss://']) {
    assert.ok(!serialized.includes(value) && !failure?.includes(value), 'Private data escaped error handling');
  }
  assert.ok(rows.some(row => 'metadata' in row && (row.metadata as { session_id?: string })?.session_id === ids[0]));
  if (mode === 'success') {
    assert.equal(failure, undefined); assert.equal(result?.title, 'Example Domain');
    assert.ok(rows.some(row => 'output' in row && (row.output as { title?: string })?.title === 'Example Domain'));
  } else {
    const prefix = mode === 'navigation' ? 'Browser task failed: navigate' : mode === 'close-timeout' ? 'Browser task failed: disconnect browser' : 'Braintrust trace flush failed';
    assert.ok(failure && failure.startsWith(prefix), 'The primary failure was replaced');
    assert.ok(failure.includes(ids[0]));
  }
  console.log(JSON.stringify({ mode, session_id: ids[0], closed: true, native_flush_calls: flushes }));
} finally {
  globalThis.fetch = originalFetch;
  for (const id of ids) {
    if (await status(id) !== 'closed') {
      const response = await originalFetch(`${process.env.NOTTE_API_URL}/sessions/${id}/stop`, {
        method: 'DELETE', headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` }, signal: AbortSignal.timeout(15_000),
      });
      assert.ok(response.ok); assert.equal(await status(id), 'closed');
    }
  }
  mock.restoreAll();
}
