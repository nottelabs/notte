import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { appendFileSync } from 'node:fs';
import { mock, test } from 'node:test';
import { promisify } from 'node:util';
import { NotteClient, sessionStatus } from 'notte-sdk';
import { chromium } from 'playwright-core';
import readPage from '../agent/tools/read_page.ts';

const live = process.env.NOTTE_EVE_LIVE === '1';
const credential = 'notte-offline-test-credential'; // pragma: allowlist secret
if (!live) process.env.NOTTE_API_KEY = credential;
const ctx = { abortSignal: new AbortController().signal } as Parameters<typeof readPage.execute>[1];

function journal(event: string, session_id: string) {
  if (process.env.NOTTE_EVE_OWNERSHIP_JOURNAL) {
    try { appendFileSync(process.env.NOTTE_EVE_OWNERSHIP_JOURNAL, JSON.stringify({ event, session_id }) + '\n', { mode: 0o600, flush: true }); }
    catch { console.warn('Ownership journal unavailable'); }
  }
}

async function closed(id: string) {
  const client = new NotteClient();
  const signal = AbortSignal.timeout(15_000);
  while (!signal.aborted) {
    const response = await sessionStatus({ client: client.getClient(), path: { session_id: id }, throwOnError: true, signal });
    if (response.data.status === 'closed') { journal('closed', id); return; }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error('The owned browser session did not close');
}

async function owned<T>(operation: () => Promise<T>, pending?: AbortController, fault?: 'reject' | 'stall'): Promise<T> {
  if (live) {
    assert.ok(process.env.NOTTE_API_KEY);
    assert.ok(process.env.NOTTE_API_URL, 'Choose the browser API explicitly');
    const ids: string[] = [];
    const originalFetch = globalThis.fetch;
    const interception = mock.method(globalThis, 'fetch', async (...args: Parameters<typeof fetch>) => {
      const [input, options] = args;
      const response = await originalFetch(input, options);
      const url = new URL(input instanceof Request ? input.url : String(input));
      if (url.pathname.endsWith('/sessions/start') && response.ok) {
        const body = await response.clone().json();
        if (typeof body.session_id === 'string') {
          ids.push(body.session_id);
          journal('allocated', body.session_id);
        }
      }
      return response;
    });
    const connect = chromium.connectOverCDP.bind(chromium);
    let closes = 0, navigationStarted = false;
    let cleanup: (() => Promise<void>) | undefined;
    const connection = pending || fault ? mock.method(chromium, 'connectOverCDP', async (...args: Parameters<typeof chromium.connectOverCDP>) => {
      const browser = await connect(...args), nativeClose = browser.close.bind(browser);
      if (pending) {
        const context = browser.contexts()[0], newPage = context.newPage.bind(context);
        context.newPage = async (...options) => {
          const page = await newPage(...options);
          await page.route('https://eve-owned.invalid/**', () => {
            navigationStarted = true;
            pending.abort();
          });
          return page;
        };
      }
      browser.close = async () => {
        closes++;
        if (pending && fault === 'stall') await new Promise<void>(() => {});
        await nativeClose();
        if (fault === 'stall') await new Promise<void>(() => {});
        if (fault === 'reject') throw new Error('PRIVATE_CLOSE_FIXTURE');
      };
      cleanup = async () => {
        let timer: ReturnType<typeof setTimeout> | undefined;
        try { await Promise.race([nativeClose(), new Promise<void>(resolve => { timer = setTimeout(resolve, 5_000); })]); }
        finally { clearTimeout(timer); }
      };
      return browser;
    }) : undefined;
    try { return await operation(); }
    finally {
      interception.mock.restore();
      connection?.mock.restore();
      try {
        for (const id of ids) {
          try { await closed(id); }
          catch (error) {
            const response = await originalFetch(`${process.env.NOTTE_API_URL}/sessions/${id}/stop`, {
              method: 'DELETE', headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` }, signal: AbortSignal.timeout(15_000),
            });
            assert.ok(response.ok, 'Owned fallback stop failed');
            await closed(id);
            throw error;
          }
        }
      } finally { if (cleanup) await cleanup(); }
      assert.equal(ids.length, 1, 'Exactly one owned browser must be allocated');
      if (pending || fault) assert.equal(closes, 1, 'Only one native disconnect should run');
      if (pending) assert.ok(navigationStarted, 'A real browser navigation must be pending before cancellation');
    }
  }
  let stopped = false, disconnected = false;
  let rejectNavigation: ((error: Error) => void) | undefined;
  const session = { getId: () => 'owned', cdpUrl: async () => `wss://example.invalid?api_key=${credential}` };
  const page = {
    goto: async (url: string) => {
      if (url === 'http://127.0.0.1:1') throw new Error(credential);
      if (pending) return await new Promise<void>((_, reject) => {
        rejectNavigation = reject;
        queueMicrotask(() => pending.abort());
      });
    },
    title: async () => 'Example Domain',
  };
  const browser = { contexts: () => [{ newPage: async () => page }], close: async () => {
    disconnected = true;
    if (fault === 'stall') await new Promise<void>(() => {});
    rejectNavigation?.(new Error('Connection closed'));
    if (fault === 'reject') throw new Error('PRIVATE_CLOSE_FIXTURE');
  } };
  const sessionMock = mock.method(NotteClient.prototype, 'Session', (() => ({
    use: async (run: (value: typeof session) => Promise<unknown>) => {
      try { return await run(session); } finally { stopped = true; }
    },
  })) as never);
  const connectionMock = mock.method(chromium, 'connectOverCDP', (async () => browser) as never);
  try { return await operation(); }
  finally {
    sessionMock.mock.restore();
    connectionMock.mock.restore();
    assert.ok(stopped, 'The owned browser must be stopped');
    assert.ok(disconnected, 'The CDP connection must close');
  }
}

test('Eve compiles and registers the native tool and its URL schema', { timeout: 120_000 }, async () => {
  let stdout: string;
  try {
    ({ stdout } = await promisify(execFile)(process.execPath, ['node_modules/eve/bin/eve.js', 'info', '--json'], { timeout: 90_000 }));
  } catch { throw new Error('Eve compilation failed; child output withheld'); }
  const info = JSON.parse(stdout);
  assert.equal(info.diagnostics.errors, 0);
  assert.ok(info.tools.includes('read_page'));
  assert.deepEqual(Object.keys(info.toolInputSchemas.root.read_page.properties), ['url']);
});

test('The native Eve tool reads a title and closes its owned browser', { timeout: 120_000 }, async () => {
  await owned(async () => {
    const result = await readPage.execute({ url: 'https://example.com' }, ctx);
    assert.ok('title' in result);
    assert.equal(result.title, 'Example Domain');
    assert.ok(result.session_id);
    assert.equal(JSON.stringify(result).includes(process.env.NOTTE_API_KEY!), false);
  });
});

test('The native Eve tool redacts navigation errors and closes its browser', { timeout: 120_000 }, async () => {
  await owned(() => assert.rejects(async () => await readPage.execute({ url: 'http://127.0.0.1:1' }, ctx), /^Error: Notte browser task failed \(session [a-z0-9-]+\)$/));
});

test('Cancellation before execution creates no browser', async () => {
  const controller = new AbortController();
  controller.abort();
  const session = mock.method(NotteClient.prototype, 'Session', () => { throw new Error('Unexpected browser creation'); });
  try {
    await assert.rejects(async () => await readPage.execute({ url: 'https://example.com' }, { ...ctx, abortSignal: controller.signal }), { name: 'AbortError' });
    assert.equal(session.mock.callCount(), 0);
  } finally { session.mock.restore(); }
});

test('Cancellation interrupts pending navigation and stops its owned browser', { timeout: live ? 120_000 : 8_000 }, async () => {
  const controller = new AbortController();
  await owned(() => assert.rejects(async () => await readPage.execute(
    { url: live ? 'https://eve-owned.invalid/pending' : 'https://example.com' }, { ...ctx, abortSignal: controller.signal },
  ), /^Error: Notte browser task failed \(session [a-z0-9-]+\)$/), controller);
  assert.ok(controller.signal.aborted);
});

for (const fault of ['reject', 'stall'] as const) {
  test(`Navigation failure remains private when disconnect ${fault}s`, { timeout: 120_000 }, async () => {
    let failure: unknown;
    await owned(async () => {
      try { await readPage.execute({ url: 'http://127.0.0.1:1' }, ctx); }
      catch (error) { failure = error; }
    }, undefined, fault);
    assert.ok(failure instanceof Error, 'The navigation must fail');
    assert.ok(/^Notte browser task failed \(session [a-z0-9-]+\)$/.test(failure.message), 'The error must remain safe');
    assert.ok(!failure.message.includes('PRIVATE_CLOSE_FIXTURE'), 'Private close diagnostics leaked');
    assert.ok(failure.cause === undefined, 'The safe error must not retain a private cause');
  });
}

test('Cancellation reaches owner cleanup when navigation and disconnect stall', { timeout: live ? 120_000 : 8_000 }, async () => {
  const controller = new AbortController();
  let failure: unknown;
  await owned(async () => {
    try {
      await readPage.execute({ url: live ? 'https://eve-owned.invalid/pending' : 'https://example.com' }, { ...ctx, abortSignal: controller.signal });
    } catch (error) { failure = error; }
  }, controller, 'stall');
  assert.ok(controller.signal.aborted);
  assert.ok(failure instanceof Error, 'The cancelled tool must reject');
  assert.ok(/^Notte browser task failed \(session [a-z0-9-]+\)$/.test(failure.message), 'The cancellation must remain safe');
});
