import assert from 'node:assert/strict';
import { mock } from 'node:test';
import { setTimeout as sleep } from 'node:timers/promises';
import * as braintrust from 'braintrust';
import { chromium } from 'playwright-core';

const api = (process.env.NOTTE_API_URL || 'https://api.notte.cc').replace(/\/$/, '');
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
const uuid = /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/;
let phase = 'run demo', failureCategory = 'none', bodyFailed = false;
let closedBeforeCompensation: boolean | null = null;
const closures: Array<{ session_id: string; closed: boolean | null }> = [];
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
  while (true) {
    closedBeforeCompensation = await status(id, signal) === 'closed';
    if (closedBeforeCompensation) return true;
    await sleep(250, undefined, { signal });
  }
};
try {
  let result: Awaited<ReturnType<typeof runDemo>> | undefined, failure: string | undefined;
  try { result = await runDemo(mode === 'navigation' ? 'not-a-valid-url' : 'https://example.com'); }
  catch (error) { failure = error instanceof Error ? error.message : 'Unknown failure'; }
  const primary = /^Browser task failed: (create browser|connect browser|navigate|disconnect browser|release browser) \[([A-Za-z][A-Za-z0-9]{0,63}(?: HTTP -?\d+)?)\] \(session (?:[a-f0-9-]{36}|not-created)\)$/.exec(failure ?? '');
  const categories = /^(?:Error|PlaywrightError|TypeError|TimeoutError|HTTPError|NotteAPIError|NotteSDKError|AssertionError)(?: HTTP [1-5]\d{2})?$/;
  failureCategory = primary && categories.test(primary[2]) ? `${primary[1]}:${primary[2]}` : failure?.startsWith('Braintrust trace flush failed (session ') ? 'trace flush' : failure ? 'other' : 'none';
  phase = 'owner counters';
  assert.equal(ids.length, 1); assert.equal(closes, 1); assert.equal(flushes, 1);
  phase = 'independent owner status';
  const closed = await waitClosed(ids[0]);
  console.log(JSON.stringify({ mode, session_id: ids[0], closed_before_compensation: closed,
    private_body: failure?.includes('PRIVATE_') ?? false, navigation_error_preserved: failure?.startsWith('Browser task failed: navigate') ?? false }));
  assert.equal(closed, true, 'Owner did not release its browser');
  phase = 'trace privacy';
  const rows = await memory.drain(), serialized = JSON.stringify(rows);
  for (const value of [process.env.NOTTE_API_KEY!, process.env.BRAINTRUST_API_KEY!, 'PRIVATE_', 'wss://']) {
    assert.ok(!serialized.includes(value) && !failure?.includes(value), 'Private data escaped error handling');
  }
  phase = 'trace metadata';
  assert.ok(rows.some(row => 'metadata' in row && (row.metadata as { session_id?: string })?.session_id === ids[0]));
  phase = 'primary result';
  if (mode === 'success') {
    assert.equal(failure, undefined); assert.equal(result?.title, 'Example Domain');
    assert.ok(rows.some(row => 'output' in row && (row.output as { title?: string })?.title === 'Example Domain'));
  } else {
    const prefix = mode === 'navigation' ? 'Browser task failed: navigate' : mode === 'close-timeout' ? 'Browser task failed: disconnect browser' : 'Braintrust trace flush failed';
    assert.ok(failure && failure.startsWith(prefix), 'The primary failure was replaced');
    assert.ok(failure.includes(ids[0]));
  }
  phase = 'passed';
  console.log(JSON.stringify({ mode, session_id: ids[0], closed: true, native_flush_calls: flushes }));
} catch (error) {
  bodyFailed = true;
  throw error;
} finally {
  globalThis.fetch = originalFetch;
  try {
    for (const id of ids) {
      assert.match(id, uuid);
      const closure = { session_id: id, closed: null as boolean | null };
      closures.push(closure);
      let closed = false;
      try { closed = await status(id) === 'closed'; } catch { /* Closure is unconfirmed; still attempt the owned stop. */ }
      if (!closed) {
        const response = await originalFetch(`${api}/sessions/${id}/stop`, {
          method: 'DELETE', headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` }, signal: AbortSignal.timeout(15_000),
        });
        assert.ok(response.ok);
      }
      closure.closed = await status(id) === 'closed';
      assert.equal(closure.closed, true);
    }
  } catch (error) {
    if (!bodyFailed) throw error;
  } finally {
    console.log(JSON.stringify({ native_cleanup_receipt: true, mode, phase,
      failure_category: failureCategory, closed_before_compensation: closedBeforeCompensation,
      closures }));
    mock.restoreAll();
  }
}
