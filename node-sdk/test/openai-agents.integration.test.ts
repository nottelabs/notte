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
  if (language === 'python' && !python) throw new Error('Set NOTTE_DOCS_PYTHON with openai-agents==0.24.0');
  const extension = language === 'python' ? 'py' : 'ts';
  const example = fileURLToPath(new URL(`../../docs/src/testers/integrations/openai_agents.${extension}`, import.meta.url));
  const runner = fileURLToPath(new URL(`../../docs/src/sniptest/run_${language}.${language === 'python' ? 'py' : 'mjs'}`, import.meta.url));
  const diagnostics = fileURLToPath(new URL('./helpers/run-openai-recipe.py', import.meta.url));
  const env = { ...process.env, ...overrides };
  return execute(language === 'python' ? python! : process.execPath,
    language === 'python' ? [diagnostics, runner, example] : ['--experimental-strip-types', runner, example],
    { env, timeout: 180_000, maxBuffer: 2 * 1024 * 1024 });
}

describe.skipIf(process.env.NOTTE_OPENAI_AGENTS_LIVE !== '1')('OpenAI Agents SDK documentation', () => {
  it.each([
    ['recipe', '../../docs/src/testers/integrations/openai_agents.py'],
    ['generated snippet', '../../docs/src/snippets/integrations/openai_agents.mdx'],
  ])('constructs matching API URLs from the %s', async (_artifact, path) => {
    const python = process.env.NOTTE_DOCS_PYTHON;
    if (!python) throw new Error('Set NOTTE_DOCS_PYTHON with openai-agents==0.24.0');
    const helper = fileURLToPath(new URL('./helpers/run-openai-recipe.py', import.meta.url));
    const { stdout } = await execute(python, [helper, '--check-api-urls', fileURLToPath(new URL(path, import.meta.url))], {
      env: { PATH: process.env.PATH, DISABLE_TELEMETRY: 'true' },
      timeout: 20_000,
    });
    expect(JSON.parse(stdout)).toEqual({ cases: 5, network_attempts: 0 });
  }, 30_000);

  it.skipIf(!process.env.OPENAI_API_KEY).each(languages)('uses the browser and closes the %s session', async language => {
    let stdout: string;
    try {
      ({ stdout } = await recipe(language));
    } catch (error) {
      const diagnostic = (error as { stderr?: string }).stderr?.match(/^OPENAI_DIAGNOSTIC=(.+)$/m)?.[1];
      if (diagnostic) throw new Error(`${language} OpenAI agent failed: ${JSON.parse(diagnostic)}`);
      throw new Error(`${language} OpenAI agent failed (SDK output withheld)`);
    }
    const { result } = JSON.parse(stdout.trim().split(/\r?\n/).at(-1)!) as {
      result: { title: string; session_id: string };
    };
    const status = await expectSessionClosed(new NotteClient(), result.session_id, `OpenAI agent ${language}`);
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
      response.end(JSON.stringify({ error: { type: 'invalid_request_error', code: 'invalid_api_key', message: 'Injected authentication failure' } }));
    });
    await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
    try {
      let output = '';
      try {
        await recipe(language, {
          OPENAI_BASE_URL: `http://127.0.0.1:${(server.address() as AddressInfo).port}/v1`,
          OPENAI_API_KEY: 'not-a-real-key', // pragma: allowlist secret
        });
        throw new Error('The framework unexpectedly accepted invalid credentials');
      } catch (error) {
        const failure = error as { stdout?: string; stderr?: string };
        output = `${failure.stdout ?? ''}\n${failure.stderr ?? ''}`;
      }
      const sessionId = output.match(/OpenAI agent failed \(session ([0-9a-f-]{36})\)/i)?.[1];
      if (!sessionId) throw new Error(`${language} did not report its owned session after failure (SDK output withheld)`);
      await expectSessionClosed(new NotteClient(), sessionId, `OpenAI agent ${language} failure`);
      expect(requests).toBeGreaterThan(0);
    } finally {
      server.closeAllConnections();
      await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
    }
  }, 200_000);
});
