import assert from 'node:assert/strict';
import { test } from 'node:test';
import { execFile } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { basename, join } from 'node:path';
import { promisify } from 'node:util';
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

test('native e2e page check releases its browser', { timeout: 90_000 }, async () => {
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
    session = await host.openSession({ name: 'real page check' });
    await session.fixtures.app.open('/');
    await expect(session.fixtures.browser).toHaveTitle('Example Domain');
    await expect(session.fixtures.screen.getByRole('link', 'Learn more')).toBeVisible();
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

test('a failing e2e CLI run releases its browser automatically', { timeout: 120_000 }, async () => {
  const directory = await mkdtemp(join(tmpdir(), 'notte-e2e-'));
  const idsFile = join(directory, 'sessions.txt');
  const configFile = join(cwd, `.${basename(directory)}.config.ts`);
  try {
    await writeFile(configFile, `
import { appendFile } from 'node:fs/promises';
import { web } from '@e2e-dev/web';
import config from './e2e.config.ts';
import { notte } from './src/notte.ts';
const provider = notte();
const tracking = { ...provider, async acquire(request) {
  const lease = await provider.acquire(request);
  await appendFile(${JSON.stringify(idsFile)}, lease.id + '\\n');
  return lease;
}};
export default { ...config, tests: ['test/fixtures/failure.e2e.ts'],
  targets: [{ name: 'notte', engine: web({ browser: tracking }), app: { url: 'https://example.com' } }] };
`);
    let exitCode: unknown;
    let output = '';
    try {
      await promisify(execFile)(process.execPath, ['node_modules/e2e/dist/cli/bin.js', 'run', '--config', configFile], {
        cwd, timeout: 90_000, env: { ...process.env, E2E_TELEMETRY_DISABLED: '1' },
      });
    } catch (error) {
      const result = error as { code?: unknown; stdout?: string; stderr?: string };
      exitCode = result.code;
      output = (result.stdout ?? '') + (result.stderr ?? '');
    }
    const ids = (await readFile(idsFile, 'utf8')).trim().split('\n').filter(Boolean);
    for (const id of ids) await assertClosed(id);
    assert.equal(ids.length, 1, 'The failing runner must acquire exactly one browser');
    assert.equal(exitCode, 1, 'The native runner must fail its deliberate assertion');
    assert.ok(output.includes('deliberate assertion failure for cleanup validation'), 'Expected fixture failure was not reported');
  } finally {
    await rm(configFile, { force: true });
    await rm(directory, { recursive: true, force: true });
  }
});
