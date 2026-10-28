import { execFile } from 'node:child_process';
import { createServer } from 'node:http';
import type { AddressInfo } from 'node:net';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { describe, expect, it } from 'vitest';
import { NotteClient } from '@/index';
import { expectSessionClosed } from './helpers/session-closure';

const execute = promisify(execFile);
const languages = ['python', 'typescript'] as const;

function recipe(language: typeof languages[number], overrides: NodeJS.ProcessEnv = {}) {
  for (const name of ['NOTTE_API_KEY', 'NOTTE_API_URL']) {
    if (!process.env[name]) throw new Error(`Set ${name} explicitly`);
  }
  const python = process.env.NOTTE_DOCS_PYTHON;
  if (language === 'python' && !python) throw new Error('Set NOTTE_DOCS_PYTHON with claude-agent-sdk==0.2.168');
  const extension = language === 'python' ? 'py' : 'ts';
  const example = fileURLToPath(new URL(`../../docs/src/testers/integrations/claude_agents.${extension}`, import.meta.url));
  const runner = fileURLToPath(new URL(`../../docs/src/sniptest/run_${language}.${language === 'python' ? 'py' : 'mjs'}`, import.meta.url));
  const env = { ...process.env, ...overrides };
  delete env.CLAUDECODE;
  return execute(language === 'python' ? python! : process.execPath,
    language === 'python' ? [runner, example] : ['--experimental-strip-types', runner, example],
    { env, timeout: 180_000, maxBuffer: 2 * 1024 * 1024 });
}

describe.skipIf(process.env.NOTTE_CLAUDE_AGENTS_LIVE !== '1')('Claude Agent SDK documentation', () => {
  it.skipIf(!process.env.ANTHROPIC_API_KEY && !process.env.ANTHROPIC_AUTH_TOKEN).each(languages)('uses the browser and closes the %s session', async language => {
    let stdout: string;
    try {
      ({ stdout } = await recipe(language));
    } catch {
      throw new Error(`${language} Claude agent failed (SDK output withheld)`);
    }
    const { result } = JSON.parse(stdout.trim().split(/\r?\n/).at(-1)!) as {
      result: { title: string; session_id: string };
    };
    const status = await expectSessionClosed(new NotteClient(), result.session_id, `Claude agent ${language}`);
    expect(result.title).toBe('Example Domain');
    // Independently verify actual browser use, rather than trusting model text.
    expect(status.steps).toEqual(expect.arrayContaining([expect.objectContaining({
      type: 'execution_result', value: expect.objectContaining({
        action: expect.objectContaining({ type: 'goto', url: expect.stringMatching(/^https:\/\/example\.com\/?$/) }), success: true,
      }),
    })]));
  }, 200_000);

  it.each(languages)('closes the %s browser after a real framework authentication error', async language => {
    let requests = 0;
    const server = createServer((_request, response) => {
      requests++;
      response.writeHead(401, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ type: 'error', error: { type: 'authentication_error', message: 'Injected authentication failure' } }));
    });
    await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
    try {
      let output = '';
      try {
        await recipe(language, {
          ANTHROPIC_BASE_URL: `http://127.0.0.1:${(server.address() as AddressInfo).port}`,
          ANTHROPIC_AUTH_TOKEN: '',
          ANTHROPIC_API_KEY: 'not-a-real-key', // pragma: allowlist secret
          CLAUDE_CODE_MAX_RETRIES: '0',
        });
        throw new Error('The framework unexpectedly accepted invalid credentials');
      } catch (error) {
        const failure = error as { stdout?: string; stderr?: string };
        output = `${failure.stdout ?? ''}\n${failure.stderr ?? ''}`;
      }
      const sessionId = output.match(/Claude agent failed \(session ([0-9a-f-]{36})\)/i)?.[1];
      if (!sessionId) throw new Error(`${language} did not report its owned session after failure (SDK output withheld)`);
      await expectSessionClosed(new NotteClient(), sessionId, `Claude agent ${language} failure`);
      expect(requests).toBeGreaterThan(0);
    } finally {
      server.closeAllConnections();
      await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
    }
  }, 200_000);
});
