import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { setTimeout as sleep } from 'node:timers/promises';

const execute = promisify(execFile);
const cwd = fileURLToPath(new URL('..', import.meta.url));
const uuid = '[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}';
const configured = Boolean(process.env.LINK_ACCESS_TOKEN && process.env.LINK_SPEND_REQUEST_ID);
if (process.env.NOTTE_LINK_REQUIRE_LIVE === '1') {
  assert.ok(process.env.NOTTE_API_KEY, 'CI requires NOTTE_API_KEY for the browser and rejection checks');
}

async function assertClosed(id: string) {
  const deadline = Date.now() + 15_000;
  while (true) {
    const response = await fetch(`${process.env.NOTTE_API_URL ?? 'https://api.notte.cc'}/sessions/${id}`, {
      headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` }, signal: AbortSignal.timeout(15_000),
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
  for (const mode of ['fixture', 'reject', 'unauthorized', 'approved']) {
    const skip = !process.env.NOTTE_API_KEY || (mode === 'approved' && !configured);
    test(`${language}: ${mode} closes its browser and withholds credentials`, { skip, timeout: 240_000 }, async () => {
      const python = process.env.NOTTE_LINK_PYTHON;
      if (language === 'python') assert.ok(python, 'Set NOTTE_LINK_PYTHON to the example virtualenv Python');
      const env: NodeJS.ProcessEnv = { ...process.env };
      if (mode !== 'approved') {
        env.LINK_ACCESS_TOKEN = 'test-link-token'; // pragma: allowlist secret
        env.LINK_SPEND_REQUEST_ID = 'lsrq_notte_fixture';
      }
      const fixture = mode === 'fixture' || mode === 'reject';
      const command = language === 'python' ? python! : process.execPath;
      const args = language === 'python'
        ? [fixture ? '../python/probe.py' : '../python/demo.py', ...(mode === 'reject' ? ['reject'] : [])]
        : [fixture ? 'test/probe.ts' : 'src/index.ts', ...(mode === 'reject' ? ['reject'] : [])];
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
      let result: { filled?: boolean; session_id?: string } | undefined;
      if (!id) {
        for (const line of output.split(/\r?\n/)) {
          try { result = JSON.parse(line); } catch { continue; }
          if (result?.session_id) { id = result.session_id; break; }
        }
      }
      try {
        assert.equal(failed, mode === 'reject' || mode === 'unauthorized', 'Recipe exited unexpectedly; SDK output withheld');
        assert.ok(id && new RegExp(`^${uuid}$`).test(id), 'Recipe did not report its owned browser');
        for (const secret of [env.NOTTE_API_KEY, env.LINK_ACCESS_TOKEN, 'PRIVATE_FIXTURE_BODY', '4000009990001984']) {
          if (secret) assert.ok(!output.includes(secret), 'Private data entered recipe output');
        }
        assert.ok(!output.includes('wss://'), 'An authenticated browser URL entered output');
        if (failed) assert.match(output, /Link form failed: retrieve and fill approved test card.*HTTP 401/);
        else assert.equal(result?.filled, true);
      } finally { if (id) await assertClosed(id); }
    });
  }
}
