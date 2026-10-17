import assert from 'node:assert/strict';
import { test } from 'node:test';
import { execFile } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { NotteClient, sessionStatus } from 'notte-sdk';
import { capturePage } from '../src/main.ts';

test('actual capture closes its owned Notte browser', { skip: process.env.NOTTE_BOX_CAPTURE_LIVE !== '1', timeout: 120_000 }, async () => {
  assert.ok(process.env.NOTTE_API_URL, 'Choose the test API explicitly');
  const original = globalThis.fetch;
  const ids: string[] = [];
  globalThis.fetch = async (input, options) => {
    const response = await original(input, options);
    const url = new URL(input instanceof Request ? input.url : String(input));
    if (url.pathname === '/sessions/start' && response.ok) ids.push((await response.clone().json()).session_id);
    return response;
  };
  try {
    const { image, sessionId } = await capturePage();
    assert.ok(image.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])));
    assert.ok(image.length > 1000);
    assert.deepEqual(ids, [sessionId]);
  } finally {
    globalThis.fetch = original;
    assert.equal(ids.length, 1);
    const client = new NotteClient();
    let closed = false;
    for (let attempt = 0; attempt < 30; attempt++) {
      const result = await sessionStatus({ client: client.getClient(), path: { session_id: ids[0] }, throwOnError: true, signal: AbortSignal.timeout(15_000) });
      if (result.data.status === 'closed') { closed = true; break; }
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    assert.ok(closed, 'Owned browser did not close');
  }
});

for (const mode of ['navigation', 'close-timeout', 'close-error']) {
  test(`native ${mode} remains private and releases its browser`, { skip: process.env.NOTTE_BOX_CAPTURE_LIVE !== '1', timeout: 90_000 }, async () => {
    const temp = await mkdtemp(join(tmpdir(), 'box-owned-test-')), journal = join(temp, 'session');
    const client = new NotteClient();
    const lookup = async (id: string) => (await sessionStatus({ client: client.getClient(), path: { session_id: id }, throwOnError: true, signal: AbortSignal.timeout(15_000) })).data.status;
    try {
      let stdout = '', stderr = '', failed = false;
      try {
        ({ stdout, stderr } = await promisify(execFile)(process.execPath, ['test/cleanup-case.ts', mode], {
          cwd: fileURLToPath(new URL('..', import.meta.url)), timeout: 45_000,
          env: { ...process.env, NOTTE_BOX_TEST_JOURNAL: journal },
        }));
      } catch { failed = true; }
      assert.equal(failed, false, 'Native browser cleanup failed; SDK output withheld');
      assert.ok(!(stdout + stderr).includes('PRIVATE_'));
      assert.ok(!(stdout + stderr).includes(process.env.NOTTE_API_KEY!));
      const result = JSON.parse(stdout.trim().split(/\r?\n/).at(-1)!);
      assert.equal(result.closed, true); assert.equal(await lookup(result.session_id), 'closed');
    } finally {
      const id = await readFile(journal, 'utf8').catch(() => undefined);
      if (id && await lookup(id) !== 'closed') {
        await client.sessions.stop(id);
        assert.equal(await lookup(id), 'closed');
      }
      await rm(temp, { recursive: true, force: true });
    }
  });
}
