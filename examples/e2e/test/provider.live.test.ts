import assert from 'node:assert/strict';
import { test } from 'node:test';
import { setTimeout as sleep } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import { web, type Browser, type BrowserProvider } from '@e2e-dev/web';
import { expect } from 'e2e';
import { openHost, type E2EHost, type E2ESession } from 'e2e/runner';
import config from '../e2e.config.ts';
import { notte } from '../src/notte.ts';

assert.ok(process.env.NOTTE_API_KEY, 'Set NOTTE_API_KEY before running live provider tests');
const cwd = fileURLToPath(new URL('../', import.meta.url));

async function assertClosed(id: string) {
  const deadline = Date.now() + 15_000;
  while (true) {
    const response = await fetch(`${process.env.NOTTE_API_URL ?? 'https://api.notte.cc'}/sessions/${id}`, {
      headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` }, signal: AbortSignal.timeout(15_000),
    });
    assert.equal(response.status, 200, 'Independent session lookup failed');
    const { status } = await response.json() as { status: string };
    if (status === 'closed') return;
    assert.equal(status, 'active', 'Unexpected session state');
    assert.ok(Date.now() < deadline, `Owned session ${id} remained active`);
    await sleep(500);
  }
}

for (const failure of [false, true]) {
  test(`native e2e ${failure ? 'assertion failure' : 'page check'} releases its browser`, { timeout: 90_000 }, async () => {
    const provider = notte();
    const ids: string[] = [];
    const tracking: BrowserProvider = {
      ...provider,
      async acquire(request) {
        const lease = await provider.acquire(request);
        ids.push(lease.id);
        return lease;
      },
    };
    let host: E2EHost<{ browser: Browser }> | undefined;
    let session: E2ESession<{ browser: Browser }> | undefined;
    try {
      host = await openHost<{ browser: Browser }>({
        cwd,
        config: {
          ...config,
          targets: [{ name: 'notte', engine: web({ browser: tracking }), app: { url: 'https://example.com' } }],
        },
      });
      session = await host.openSession({ name: failure ? 'real assertion failure' : 'real page check' });
      await session.fixtures.app.open('/');
      if (failure) {
        const browser = session.fixtures.browser;
        await assert.rejects(async () => { await expect(browser).toHaveTitle('This title does not exist'); });
      } else {
        await expect(session.fixtures.browser).toHaveTitle('Example Domain');
        await expect(session.fixtures.screen.getByRole('link', 'Learn more')).toBeVisible();
      }
    } finally {
      try {
        if (session) assert.equal((await session.close()).length, 0, 'Native session cleanup failed');
      } finally {
        try {
          if (host) assert.equal((await host.close()).length, 0, 'Native host cleanup failed');
        } finally {
          for (const id of ids) await assertClosed(id);
        }
      }
    }
    assert.equal(ids.length, 1, 'Each native test must lease its own Notte browser');
  });
}
