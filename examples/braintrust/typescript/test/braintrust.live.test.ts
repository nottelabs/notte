import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { setTimeout as sleep } from 'node:timers/promises';
import { initLogger } from 'braintrust';

const execute = promisify(execFile);
const live = Boolean(process.env.NOTTE_API_KEY && process.env.BRAINTRUST_API_KEY);
const cwd = fileURLToPath(new URL('..', import.meta.url));
const uuid = /[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}/;

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

async function persistedTrace(sessionId: string) {
  assert.match(sessionId, new RegExp(`^${uuid.source}$`));
  const logger = initLogger({ projectName: process.env.BRAINTRUST_PROJECT ?? 'notte-integration-tests' });
  const projectId = await logger.id;
  assert.match(projectId, new RegExp(`^${uuid.source}$`));
  const query = `SELECT id, output, metadata, metrics, error, span_attributes FROM project_logs('${projectId}') WHERE metadata.session_id = '${sessionId}' LIMIT 1`;
  const deadline = Date.now() + 30_000;
  while (true) {
    const response = await fetch(`${process.env.BRAINTRUST_API_URL ?? 'https://api.braintrust.dev'}/btql`, {
      method: 'POST', headers: { Authorization: `Bearer ${process.env.BRAINTRUST_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }), signal: AbortSignal.timeout(15_000),
    });
    assert.equal(response.status, 200, 'Braintrust trace query failed');
    const { data } = await response.json() as { data: Array<{
      output?: { title?: string }; error?: string; metadata: { session_id: string };
      metrics: { start: number; end: number }; span_attributes: { name: string };
    }> };
    if (data.length) {
      const row = data[0];
      assert.equal(row.metadata.session_id, sessionId);
      assert.equal(row.span_attributes.name, 'notte.browser');
      assert.ok(row.metrics.end >= row.metrics.start);
      const serialized = JSON.stringify(row);
      for (const name of ['NOTTE_API_KEY', 'BRAINTRUST_API_KEY']) {
        assert.ok(!serialized.includes(process.env[name]!), 'A credential entered the trace');
      }
      assert.ok(!serialized.includes('wss://'), 'An authenticated browser URL entered the trace');
      return row;
    }
    assert.ok(Date.now() < deadline, 'Braintrust did not persist the trace');
    await sleep(500);
  }
}

for (const language of ['python', 'typescript']) {
  for (const failure of [false, true]) {
    test(`${language}: ${failure ? 'navigation error' : 'title'} trace persists and browser closes`, { skip: !live, timeout: 240_000 }, async () => {
      const python = process.env.NOTTE_BRAINTRUST_PYTHON;
      if (language === 'python') assert.ok(python, 'Set NOTTE_BRAINTRUST_PYTHON to the example virtualenv Python');
      const url = failure ? 'not-a-valid-url' : 'https://example.com';
      const command = language === 'python' ? python! : process.execPath;
      const args = language === 'python' ? ['../python/demo.py', url] : ['src/index.ts', url];
      let stdout = '';
      let stderr = '';
      let failed = false;
      try {
        ({ stdout, stderr } = await execute(command, args, { cwd, env: process.env, timeout: 180_000 }));
      } catch (error) {
        failed = true;
        const child = error as { stdout?: string; stderr?: string };
        stdout = child.stdout ?? '';
        stderr = child.stderr ?? '';
      }
      let id = new RegExp(`\\(session (${uuid.source})\\)`).exec(stdout + stderr)?.[1];
      if (!id) {
        try { id = JSON.parse(stdout.trim().split(/\r?\n/).at(-1)!).session_id; } catch { /* The failure assertion below reports malformed output. */ }
      }
      try {
        assert.equal(failed, failure, 'Original recipe exited unexpectedly; SDK output withheld');
        if (failure) {
          id = new RegExp(`\\(session (${uuid.source})\\)`).exec(stdout + stderr)?.[1];
          assert.ok(id, 'Recipe did not report its owned browser');
          const row = await persistedTrace(id);
          assert.ok(row.error?.includes('Browser task failed: navigate'));
        } else {
          const result = JSON.parse(stdout.trim().split(/\r?\n/).at(-1)!);
          id = result.session_id;
          assert.equal(result.title, 'Example Domain');
          assert.ok(result.span_id && result.trace_url);
          const row = await persistedTrace(id!);
          assert.equal(row.output?.title, 'Example Domain');
          assert.ok(!row.error);
        }
      } finally { if (id) await assertClosed(id); }
    });
  }
}
