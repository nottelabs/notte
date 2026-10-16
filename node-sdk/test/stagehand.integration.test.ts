import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { describe, expect, it } from 'vitest';
import { NotteClient } from '@/index';
import { expectSessionClosed } from './helpers/session-closure';

const execute = promisify(execFile);

// Executes the published recipes unchanged. It provisions sessions and calls
// Anthropic, so the shared credential-free/staging suites do not opt in.
describe.skipIf(process.env.NOTTE_STAGEHAND_LIVE !== '1')('Stagehand v4 documentation', () => {
  it.each(['python', 'typescript'] as const)('extracts and closes the %s session', async (language) => {
    for (const name of ['NOTTE_API_KEY', 'NOTTE_API_URL', 'ANTHROPIC_API_KEY']) {
      if (!process.env[name]) throw new Error(`Set ${name} explicitly`);
    }
    const python = process.env.NOTTE_DOCS_PYTHON;
    if (language === 'python' && !python) throw new Error('Set NOTTE_DOCS_PYTHON to the environment with stagehand==4.2.1');
    const extension = language === 'python' ? 'py' : 'ts';
    const example = fileURLToPath(new URL(`../../docs/src/testers/integrations/stagehand_connect.${extension}`, import.meta.url));
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
      throw new Error(`${language} Stagehand example failed (SDK output withheld)`);
    }
    const { result } = JSON.parse(stdout.trim().split(/\r?\n/).at(-1)!) as {
      result: { heading: string; session_id: string };
    };
    expect(result.session_id).toBeTruthy();
    await expectSessionClosed(new NotteClient(), result.session_id, `Stagehand ${language}`);
    expect(result.heading).toBe('Example Domain');
  }, 200_000);
});
