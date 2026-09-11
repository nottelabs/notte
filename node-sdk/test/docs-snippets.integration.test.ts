import { execFile } from 'node:child_process';
import { readdir, readFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { NotteClient, functionCreate, functionDelete, listFunctionRunsByFunctionId, functionRunStop, sessionStatus } from '@/index';
import { collectExampleResult, verifyExampleOutput, type ExampleContract } from './helpers/docs-examples';

const execute = promisify(execFile);
const testers = fileURLToPath(new URL('../../docs/src/testers/', import.meta.url));
const contracts = JSON.parse(await readFile(new URL('../../docs/src/sniptest/live-examples.json', import.meta.url), 'utf8')) as Record<string, ExampleContract>;
const catalog = JSON.parse(await readFile(`${testers}snippets.json`, 'utf8')) as Record<string, {
  blocks: Array<{ source: string; execution_pending?: string }>;
}>;
const pending = new Set(Object.values(catalog).flatMap(spec => spec.blocks)
  .filter(block => block.execution_pending).map(block => block.source));
const snippets = (await readdir(testers, { recursive: true }))
  .filter(name => name.endsWith('.ts') && !pending.has(name)).sort();

// Opt in explicitly: this suite provisions live resources and requires a built SDK.
describe.skipIf(process.env.NOTTE_DOCS_LIVE !== '1')('paired documentation examples', () => {
  let client: NotteClient;
  let functionId: string | undefined;
  const originalFunctionId = process.env.NOTTE_FUNCTION_ID;

  beforeAll(async () => {
    if (!process.env.NOTTE_API_KEY || !process.env.NOTTE_API_URL) {
      throw new Error('Set NOTTE_API_KEY and NOTTE_API_URL explicitly for live docs tests');
    }
    client = new NotteClient();
    const created = await functionCreate({
      client: client.getClient(),
      body: { file: new File([
        'def run(url: str, search_query: str = "", fail: bool = False) -> dict:\n    print("Running docs echo")\n    if fail:\n        raise ValueError("Example function failure")\n    return {"url": url, "search_query": search_query}\n',
      ], 'docs_echo.py', { type: 'text/x-python' }) },
      throwOnError: true,
    });
    functionId = created.data.function_id;
    process.env.NOTTE_FUNCTION_ID = functionId;
  }, 60_000);

  afterAll(async () => {
    if (originalFunctionId === undefined) delete process.env.NOTTE_FUNCTION_ID;
    else process.env.NOTTE_FUNCTION_ID = originalFunctionId;
    if (!functionId) return;
    try {
      let hasNext = true;
      for (let page = 1; hasNext; page++) {
        const runs = await listFunctionRunsByFunctionId({
          client: client.getClient(), path: { function_id: functionId }, query: { page }, throwOnError: true,
        });
        hasNext = runs.data.has_next;
        for (const run of runs.data.items) {
          if (run.status === 'active') {
            await functionRunStop({ client: client.getClient(), path: { function_id: functionId, run_id: run.function_run_id }, throwOnError: true });
          }
        }
      }
    } finally {
      await functionDelete({ client: client.getClient(), path: { function_id: functionId }, throwOnError: true });
    }
  }, 60_000);

  it.each(snippets)('%s and its Python counterpart execute unchanged', { timeout: 180_000 }, async name => {
    if (name === 'quickstart/cdp_session.ts') {
      const directory = await mkdtemp(join(tmpdir(), 'notte-docs-screenshots-'));
      const original = process.env.NOTTE_SCREENSHOT_PATH;
      try {
        const typescriptPath = join(directory, 'typescript.png');
        const pythonPath = join(directory, 'python.png');
        process.env.NOTTE_SCREENSHOT_PATH = typescriptPath;
        await import(/* @vite-ignore */ `${testers}${name}`);
        await execute(process.env.NOTTE_DOCS_PYTHON || 'python', [`${testers}${name.replace(/\.ts$/, '.py')}`], {
          env: { ...process.env, NOTTE_SCREENSHOT_PATH: pythonPath }, timeout: 120_000,
        });
        for (const path of [typescriptPath, pythonPath]) {
          const png = await readFile(path);
          expect(png.subarray(0, 8)).toEqual(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
          expect(png.length).toBeGreaterThan(1000);
        }
      } finally {
        if (original === undefined) delete process.env.NOTTE_SCREENSHOT_PATH;
        else process.env.NOTTE_SCREENSHOT_PATH = original;
        await rm(directory, { recursive: true, force: true });
      }
      return;
    }
    const logged: unknown[][] = [];
    const contract = contracts[name];
    let exported: Record<string, unknown>;
    const log = vi.spyOn(console, 'log').mockImplementation((...args) => { logged.push(args); });
    try {
      exported = await import(/* @vite-ignore */ `${testers}${name}`);
    } finally {
      log.mockRestore();
    }
    const pythonPath = `${testers}${name.replace(/\.ts$/, '.py')}`;
    const pythonArgs = contract
      ? [fileURLToPath(new URL('../../docs/src/sniptest/run_python.py', import.meta.url)), pythonPath]
      : [pythonPath];
    const { stdout, stderr } = await execute(process.env.NOTTE_DOCS_PYTHON || 'python', pythonArgs, {
      env: process.env,
      timeout: 120_000,
      maxBuffer: 2 * 1024 * 1024,
    });
    if (contract) {
      const pythonValues = JSON.parse(stdout.trim().split(/\r?\n/).at(-1)!);
      const ids = [
        verifyExampleOutput(JSON.stringify(collectExampleResult(exported!, contract)), contract, logged.map(args => args.join(' ')).join('\n')),
        verifyExampleOutput(JSON.stringify(collectExampleResult(pythonValues, contract)), contract, `${stdout}\n${stderr}`),
      ];
      if (contract.closedSession) {
        expect(ids[0]).not.toBe(ids[1]);
        for (const id of ids) {
          const session = await sessionStatus({ client: client.getClient(), path: { session_id: id! }, throwOnError: true });
          expect(session.data.status).toBe('closed');
        }
      }
      return;
    }
    if (name.startsWith('functions/')) {
      const query = name.endsWith('invoke_sdk.ts') ? 'laptop' : '';
      expect(logged).toContainEqual([{ url: 'https://example.com', search_query: query }]);
      expect(stdout).toContain(`{'url': 'https://example.com', 'search_query': '${query}'}`);
      if (name.endsWith('async_create_start.ts')) {
        expect(logged.flat()).toContain('closed');
        expect(stdout).toContain('closed');
      }
    }
    if (name === 'sessions/lifecycle/context_manager.ts') {
      const ids = [logged[0][0], stdout.trim()];
      for (const id of ids) {
        expect(typeof id).toBe('string');
        const session = await sessionStatus({ client: client.getClient(), path: { session_id: id as string }, throwOnError: true });
        expect(session.data.status).toBe('closed');
      }
    }
  });
});
