import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { setTimeout as sleep } from 'node:timers/promises';
import { Secrets } from '@1password/sdk';

const execute = promisify(execFile);
const cwd = fileURLToPath(new URL('..', import.meta.url));
const uuid = '[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}';
const configured = ['OP_SERVICE_ACCOUNT_TOKEN', 'OP_USERNAME_REF', 'OP_PASSWORD_REF'].every(name => process.env[name]);

test('the installed native SDK accepts valid references and rejects malformed ones', () => {
  Secrets.validateSecretReference('op://NotteIntegrationTests/BrowserLogin/username');
  assert.throws(() => Secrets.validateSecretReference('not-a-reference'));
});

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
  for (const failure of [false, true]) {
    const skip = !process.env.NOTTE_API_KEY || (!failure && !configured);
    test(`${language}: ${failure ? 'native authentication rejection' : 'vault fields fill and submit'} closes its browser`, { skip, timeout: 240_000 }, async () => {
      const python = process.env.NOTTE_ONEPASSWORD_PYTHON;
      if (language === 'python') assert.ok(python, 'Set NOTTE_ONEPASSWORD_PYTHON to the example virtualenv Python');
      const env: NodeJS.ProcessEnv = {
        ...process.env,
        OP_USERNAME_REF: process.env.OP_USERNAME_REF || 'op://NotteIntegrationTests/BrowserLogin/username',
        OP_PASSWORD_REF: process.env.OP_PASSWORD_REF || 'op://NotteIntegrationTests/BrowserLogin/password',
      };
      if (failure) env.OP_SERVICE_ACCOUNT_TOKEN = 'test-invalid-token'; // pragma: allowlist secret
      const command = language === 'python' ? python! : process.execPath;
      const args = language === 'python' ? ['../python/demo.py'] : ['src/index.ts'];
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
      let result: { submitted?: boolean; session_id?: string } | undefined;
      if (!id) {
        for (const line of output.split(/\r?\n/)) {
          try { result = JSON.parse(line); } catch { continue; }
          if (result?.session_id) { id = result.session_id; break; }
        }
      }
      try {
        assert.equal(failed, failure, 'Original recipe exited unexpectedly; SDK output withheld');
        assert.ok(id && new RegExp(`^${uuid}$`).test(id), 'Recipe did not report its owned browser');
        for (const name of ['NOTTE_API_KEY', 'OP_SERVICE_ACCOUNT_TOKEN']) {
          const secret = env[name];
          if (secret) assert.ok(!output.includes(secret), 'A credential entered recipe output');
        }
        assert.ok(!output.includes('wss://'), 'An authenticated browser URL entered recipe output');
        if (failure) assert.match(output, /Vault form failed: resolve and fill login/);
        else assert.equal(result?.submitted, true);
      } finally { if (id) await assertClosed(id); }
    });
  }
}

for (const language of ['python', 'typescript']) {
  for (const mode of ['reject', 'timeout']) {
    test(`${language}: native authentication failure survives ${mode} disconnect`, { skip: !process.env.NOTTE_API_KEY, timeout: 90_000 }, async () => {
      const python = process.env.NOTTE_ONEPASSWORD_PYTHON;
      if (language === 'python') assert.ok(python, 'Set NOTTE_ONEPASSWORD_PYTHON');
      const command = language === 'python' ? python! : process.execPath;
      const args = language === 'python' ? ['../python/cleanup_case.py', mode] : ['test/cleanup-case.ts', mode];
      let output = '', failed = false;
      try {
        const result = await execute(command, args, { cwd, timeout: 60_000, env: {
          ...process.env,
          OP_SERVICE_ACCOUNT_TOKEN: 'test-invalid-token', // pragma: allowlist secret
          OP_USERNAME_REF: 'op://NotteIntegrationTests/BrowserLogin/username',
          OP_PASSWORD_REF: 'op://NotteIntegrationTests/BrowserLogin/password', // pragma: allowlist secret
        } });
        output = result.stdout + result.stderr;
      } catch (error) {
        failed = true;
        const child = error as { stdout?: string; stderr?: string };
        output = (child.stdout ?? '') + (child.stderr ?? '');
      }
      const records = output.split(/\r?\n/).flatMap(line => {
        try { return [JSON.parse(line) as { session_id?: string; closed?: boolean }]; } catch { return []; }
      });
      const id = records.find(record => record.session_id)?.session_id;
      try {
        assert.equal(failed, false, 'Native cleanup case failed; SDK output withheld');
        assert.ok(id && records.some(record => record.closed === true));
        for (const value of [process.env.NOTTE_API_KEY!, 'PRIVATE_', 'test-invalid-token', 'wss://']) {
          assert.ok(!output.includes(value), 'Private data reached recipe output');
        }
      } finally { if (id) await assertClosed(id); }
    });
  }
}
