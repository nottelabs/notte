import { execFile } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { expect, it, vi } from 'vitest';

const execute = promisify(execFile);
const runner = fileURLToPath(new URL('../../docs/src/sniptest/run_typescript.mjs', import.meta.url));

it('resolves only the explicit Playwright peer from the local SDK', async () => {
  const loader = new URL('../../docs/src/sniptest/typescript-loader.mjs', import.meta.url).href;
  const { resolve } = await import(/* @vite-ignore */ loader);
  const nextResolve = vi.fn(() => ({ url: 'resolved' }));
  const context = { parentURL: 'file:///tmp/owned-fixture/example.ts', conditions: ['node', 'import'] };
  resolve('playwright-core', context, nextResolve);
  expect(nextResolve).toHaveBeenLastCalledWith('playwright-core', {
    ...context, parentURL: new URL('../package.json', import.meta.url).href,
  });
  resolve('unrelated-package', context, nextResolve);
  expect(nextResolve).toHaveBeenLastCalledWith('unrelated-package', context);
  expect(context.parentURL).toBe('file:///tmp/owned-fixture/example.ts');
});

it('imports Playwright in an isolated artifact example without launching a browser', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'notte-runner-playwright-'));
  try {
    const source = join(directory, 'example.ts');
    await writeFile(source, "import { chromium } from 'playwright-core';\nexport const results = chromium.name();\n");
    const { stdout } = await execute(process.execPath, ['--experimental-strip-types', runner, source], { cwd: directory });
    expect(JSON.parse(stdout.trim().split('\n').at(-1)!)).toEqual({ results: 'chromium' });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

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
