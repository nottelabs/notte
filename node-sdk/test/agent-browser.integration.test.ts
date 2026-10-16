import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { describe, expect, it } from 'vitest';
import { NotteClient } from '@/index';
import { expectSessionClosed } from './helpers/session-closure';

const execute = promisify(execFile);

// Executes the published recipes unchanged against an explicitly selected API.
// The caller must put agent-browser@0.39.1 on PATH.
describe.skipIf(process.env.NOTTE_AGENT_BROWSER_LIVE !== '1')('agent-browser documentation', () => {
  it.each(['python', 'typescript'] as const)('extracts and closes the %s session', async (language) => {
    for (const name of ['NOTTE_API_KEY', 'NOTTE_API_URL']) {
      if (!process.env[name]) throw new Error(`Set ${name} explicitly`);
    }
    const python = process.env.NOTTE_DOCS_PYTHON;
    if (language === 'python' && !python) throw new Error('Set NOTTE_DOCS_PYTHON to the environment with notte-sdk');
    const extension = language === 'python' ? 'py' : 'ts';
    const example = fileURLToPath(new URL(`../../docs/src/testers/integrations/agent_browser.${extension}`, import.meta.url));
    const runner = fileURLToPath(new URL(`../../docs/src/sniptest/run_${language}.${language === 'python' ? 'py' : 'mjs'}`, import.meta.url));
    let stdout: string;
    try {
      ({ stdout } = await execute(
        language === 'python' ? python! : process.execPath,
        language === 'python' ? [runner, example] : ['--experimental-strip-types', runner, example],
        { env: process.env, timeout: 180_000, maxBuffer: 2 * 1024 * 1024 },
      ));
    } catch {
      // SDK error output can contain authenticated CDP URLs or provider keys.
      throw new Error(`${language} agent-browser example failed (SDK output withheld)`);
    }
    const { result } = JSON.parse(stdout.trim().split(/\r?\n/).at(-1)!) as {
      result: { title: string; session_id: string };
    };
    expect(result.session_id).toBeTruthy();
    await expectSessionClosed(new NotteClient(), result.session_id, `agent-browser ${language}`);
    expect(result.title).toBe('Example Domain');
  }, 200_000);
});

// Own the fixture DOM so selector checks do not depend on a public site's markup.
describe.skipIf(process.env.NOTTE_AGENT_BROWSER_LIVE !== '1')('agent-browser lifecycle', () => {
  it.each(['application', 'native'] as const)('fills, clicks, reconnects, and stops after a %s error', async mode => {
    const client = new NotteClient();
    let sessionId = '';
    try {
      await expect(client.Session().use(async (session) => {
        sessionId = session.getId()!;
        const command = ['--session', `notte-${sessionId}`, '--json'];
        const env = { ...process.env, AGENT_BROWSER_CDP: await session.cdpUrl(), AGENT_BROWSER_DEFAULT_TIMEOUT: '1000' };
        const failedCommands: string[] = [];
        async function browser(...args: string[]) {
          try {
            const { stdout } = await execute('agent-browser', [...command, ...args], { env, timeout: 120_000 });
            const response = JSON.parse(stdout);
            if (!response.success) throw new Error('Unsuccessful CLI command');
            return response.data;
          } catch {
            failedCommands.push(args[0]);
            throw new Error(`agent-browser ${args[0]} failed (failed commands: ${failedCommands.join(', ')}; CLI output withheld)`);
          }
        }
        let failed = false;
        try {
          await browser('open', 'data:text/html,<label>Name<input id="name"></label><button id="save" onclick="document.getElementById(\'result\').textContent=\'Saved \'+document.getElementById(\'name\').value">Save</button><p id="result"></p>');
          expect((await browser('snapshot', '-i')).snapshot).toContain('Save');
          await browser('fill', '#name', 'Ada');
          await browser('click', '#save');
          expect((await browser('get', 'text', '#result')).text).toBe('Saved Ada');
          await browser('close');
          expect((await session.status()).status).toBe('active');
          expect((await browser('get', 'text', '#result')).text).toBe('Saved Ada');
          if (mode === 'native') await browser('get', 'text', '#missing-owned-fixture');
          throw new Error('Injected application failure');
        } catch (error) {
          failed = true;
          throw error;
        } finally {
          try { await browser('close'); }
          catch (error) { if (!failed) throw error; }
        }
      })).rejects.toThrow(mode === 'native' ? 'agent-browser get failed' : 'Injected application failure');
      expect(sessionId).toBeTruthy();
    } finally {
      if (sessionId) await expectSessionClosed(client, sessionId, 'agent-browser application failure');
    }
  }, 200_000);
});
