import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mock, test } from 'node:test';
import { promisify } from 'node:util';
import { NotteClient, Session, sessionStatus } from 'notte-sdk';
import { chromium } from 'playwright-core';
import readPage from '../agent/tools/read_page.ts';

const live = process.env.NOTTE_EVE_LIVE === '1';
const credential = 'notte-offline-test-credential'; // pragma: allowlist secret
if (!live) process.env.NOTTE_API_KEY = credential;
const ctx = { abortSignal: new AbortController().signal } as Parameters<typeof readPage.execute>[1];

async function closed(id: string) {
  const client = new NotteClient();
  const signal = AbortSignal.timeout(15_000);
  while (!signal.aborted) {
    const response = await sessionStatus({ client: client.getClient(), path: { session_id: id }, throwOnError: true, signal });
    if (response.data.status === 'closed') return;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error('The owned browser session did not close');
}

async function owned(operation: () => Promise<unknown>, pending?: AbortController) {
  if (live) {
    assert.ok(process.env.NOTTE_API_KEY);
    assert.ok(process.env.NOTTE_API_URL, 'Choose the browser API explicitly');
    const ids: string[] = [], stop = Session.prototype.stop;
    const interception = mock.method(Session.prototype, 'stop', async function (this: Session, ...args: Parameters<Session['stop']>) {
      ids.push(this.getId()!);
      return await stop.apply(this, args);
    });
    try { await operation(); }
    finally {
      interception.mock.restore();
      assert.equal(ids.length, 1, 'Exactly one owned browser must be stopped');
      await closed(ids[0]);
    }
    return;
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
    rejectNavigation?.(new Error('Connection closed'));
  } };
  const sessionMock = mock.method(NotteClient.prototype, 'Session', (() => ({
    use: async (run: (value: typeof session) => Promise<unknown>) => {
      try { return await run(session); } finally { stopped = true; }
    },
  })) as never);
  const connectionMock = mock.method(chromium, 'connectOverCDP', (async () => browser) as never);
  try { await operation(); }
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

test('Cancellation interrupts pending navigation and stops its owned browser', { skip: live, timeout: 5_000 }, async () => {
  const controller = new AbortController();
  await owned(() => assert.rejects(async () => await readPage.execute(
    { url: 'https://example.com' }, { ...ctx, abortSignal: controller.signal },
  ), /^Error: Notte browser task failed \(session owned\)$/), controller);
  assert.ok(controller.signal.aborted);
});
