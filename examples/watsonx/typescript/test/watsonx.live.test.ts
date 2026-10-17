import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { setTimeout as sleep } from 'node:timers/promises';

const execute = promisify(execFile);
const cwd = fileURLToPath(new URL('..', import.meta.url));
const uuid = '[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}';
if (process.env.NOTTE_WATSONX_REQUIRE_LIVE === '1') {
  assert.ok(process.env.NOTTE_API_KEY, 'CI requires NOTTE_API_KEY for the browser and rejection checks');
}

async function assertClosed(id: string) {
  const deadline = Date.now() + 15_000;
  const signal = AbortSignal.timeout(15_000);
  while (true) {
    const response = await fetch(`${process.env.NOTTE_API_URL ?? 'https://api.notte.cc'}/sessions/${id}`, {
      headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` }, signal,
    });
    assert.equal(response.status, 200, 'Authoritative session lookup failed');
    const { status } = await response.json() as { status: string };
    if (status === 'closed') return;
    assert.equal(status, 'active');
    assert.ok(Date.now() < deadline, 'Owned browser remained active');
    await sleep(500);
  }
}

for (const language of ['python', 'typescript']) {
  for (const mode of ['fixture', 'iam-reject', 'chat-reject', 'iam-reject-close', 'iam-reject-timeout']) {
    const skip = !process.env.NOTTE_API_KEY;
    test(`${language}: ${mode} closes its browser and withholds credentials`, { skip, timeout: 240_000 }, async () => {
      const python = process.env.NOTTE_WATSONX_PYTHON;
      if (language === 'python') assert.ok(python, 'Set NOTTE_WATSONX_PYTHON to the example virtualenv Python');
      const env: NodeJS.ProcessEnv = { ...process.env };
      env.WATSONX_API_KEY = 'fixture-api-key'; // pragma: allowlist secret
      env.WATSONX_PROJECT_ID = 'fixture-project';
      env.WATSONX_MODEL_ID = 'fixture-model';
      const command = language === 'python' ? python! : process.execPath;
      const args = language === 'python' ? ['../python/probe.py', mode] : ['test/probe.ts', mode];
      let output = '';
      let failed = false;
      try {
        const result = await execute(command, args, { cwd, env, timeout: 180_000 });
        output = result.stdout + result.stderr;
      } catch (error) {
        failed = true;
        const result = error as { stdout?: string; stderr?: string };
        output = (result.stdout ?? '') + (result.stderr ?? '');
      }
      let id = new RegExp(`\\(session (${uuid})\\)`).exec(output)?.[1];
      let result: { description?: string; session_id?: string } | undefined;
      if (!id) {
        for (const line of output.split(/\r?\n/)) {
          let row: { description?: string; session_id?: string } | null;
          try { row = JSON.parse(line); } catch { continue; }
          if (row?.session_id) id = row.session_id;
          if (row?.description !== undefined) result = row;
        }
      }
      try {
        if (process.env.WATSONX_EVIDENCE_DIR) {
          mkdirSync(process.env.WATSONX_EVIDENCE_DIR, { recursive: true, mode: 0o700 });
          writeFileSync(join(process.env.WATSONX_EVIDENCE_DIR, `${language}-${mode}.log`), output, { mode: 0o600 });
        }
        assert.equal(failed, mode !== 'fixture', 'Recipe exited unexpectedly; SDK output withheld');
        assert.ok(id && new RegExp(`^${uuid}$`).test(id), 'Recipe did not report its owned browser');
        for (const secret of [env.NOTTE_API_KEY, env.WATSONX_API_KEY, 'PRIVATE_FIXTURE_BODY', 'PRIVATE_CLOSE_FIXTURE', 'fixture-bearer']) {
          if (secret) assert.ok(!output.includes(secret), 'Private data entered recipe output');
        }
        assert.ok(!output.includes('wss://'), 'An authenticated browser URL entered output');
        if (failed) assert.match(output, new RegExp(`Screenshot analysis failed: describe screenshot.*HTTP ${mode.startsWith('iam-reject') ? 401 : 403}`));
        else assert.equal(result?.description, 'Visible page description');
      } finally {
        if (id) {
          let closed = false;
          try { await assertClosed(id); closed = true; }
          finally {
            if (!closed) {
              const response = await fetch(`${process.env.NOTTE_API_URL ?? 'https://api.notte.cc'}/sessions/${id}/stop`, {
                method: 'DELETE', headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` }, signal: AbortSignal.timeout(15_000),
              });
              assert.ok(response.ok, 'Owned fallback stop failed');
              await assertClosed(id);
            }
          }
        }
      }
    });
  }
}
