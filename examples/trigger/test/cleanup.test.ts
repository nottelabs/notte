import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { mock, test } from 'node:test';
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';
import { readPage } from '../src/trigger/read-page.ts';

for (const mode of ['success', 'navigation', 'close', 'both', 'connection', 'stalled_close']) {
  test(`owned handler cleanup: ${mode}`, { timeout: 10_000 }, async () => {
    const privateUrl = 'wss://fixture.invalid/browser?capability=private-fixture';
    const previousKey = process.env.NOTTE_API_KEY;
    process.env.NOTTE_API_KEY = randomUUID();
    let closed = false;
    let disconnects = 0;
    const session = {
      getId: () => 'owned-fixture',
      cdpUrl: async () => privateUrl,
    };
    const owner = { use: async (run: (value: typeof session) => Promise<unknown>) => {
      try { return await run(session); }
      finally { closed = true; }
    } };
    const page = {
      goto: async () => { if (['navigation', 'both'].includes(mode)) throw new Error(privateUrl); },
      title: async () => 'Example Domain',
    };
    const browser = {
      contexts: () => [{ newPage: async () => page }],
      close: async () => {
        disconnects++;
        if (['close', 'both'].includes(mode)) throw new Error(privateUrl);
        if (mode === 'stalled_close') await new Promise(() => {});
      },
    };
    const sessionMock = mock.method(NotteClient.prototype, 'Session', () => owner as unknown as ReturnType<NotteClient['Session']>);
    const connectMock = mock.method(chromium, 'connectOverCDP', async () => {
      if (mode === 'connection') throw new Error(privateUrl);
      return browser as unknown as Awaited<ReturnType<typeof chromium.connectOverCDP>>;
    });
    try {
      if (mode === 'success') assert.deepEqual(await readPage({ url: 'https://example.com' }), { title: 'Example Domain', session_id: 'owned-fixture' });
      else {
        const expected = ['close', 'stalled_close'].includes(mode) ? 'cleanup failed' : `task failed during ${mode === 'connection' ? 'browser connection' : 'navigation'}`;
        await assert.rejects(readPage({ url: 'https://example.com' }), (error: unknown) => {
          assert.ok(error instanceof Error);
          assert.ok(error.message.includes(expected), 'The primary failure must survive disconnect errors');
          assert.ok(error.message.includes('owned-fixture'));
          assert.ok(!error.message.includes(privateUrl), 'Raw connection details must remain private');
          return true;
        });
      }
      assert.equal(disconnects, mode === 'connection' ? 0 : 1);
      assert.equal(closed, true, 'The surrounding owner must close after every outcome');
    } finally {
      connectMock.mock.restore();
      sessionMock.mock.restore();
      if (previousKey === undefined) delete process.env.NOTTE_API_KEY;
      else process.env.NOTTE_API_KEY = previousKey;
    }
  });
}
