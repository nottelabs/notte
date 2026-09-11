import { execFile } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { expect, it } from 'vitest';

const execute = promisify(execFile);
const runner = fileURLToPath(new URL('../../docs/src/sniptest/run_typescript.mjs', import.meta.url));

it('executes TypeScript unchanged in an isolated fixture directory and captures exports', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'notte-runner-test-'));
  try {
    const source = join(directory, 'example.ts');
    const content = "import { readFile } from 'node:fs/promises';\nconsole.log('original output');\nexport const results: string = await readFile('fixture.txt', 'utf8');\n";
    await writeFile(source, content);
    await writeFile(join(directory, 'fixture.txt'), 'owned fixture');
    const { stdout } = await execute(process.execPath, ['--experimental-strip-types', runner, source], { cwd: directory });
    expect(stdout).toContain('original output');
    expect(JSON.parse(stdout.trim().split('\n').at(-1)!)).toEqual({ results: 'owned fixture' });
    expect(await readFile(source, 'utf8')).toBe(content);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

it('propagates example assertion failures instead of reporting a successful capture', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'notte-runner-test-'));
  try {
    const source = join(directory, 'failure.ts');
    await writeFile(source, "throw new Error('fixture failure');\nexport {};\n");
    await expect(execute(process.execPath, ['--experimental-strip-types', runner, source], { cwd: directory })).rejects.toMatchObject({ code: 1 });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
