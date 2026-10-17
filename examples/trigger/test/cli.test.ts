import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);
const cliPackage = require.resolve('trigger.dev/package.json');
const cliRequire = createRequire(cliPackage);
const c12Require = createRequire(cliRequire.resolve('c12'));
const gigetPath = c12Require.resolve('giget');
const gigetRequire = createRequire(gigetPath);

test('the pinned CLI loads this project configuration', { timeout: 60_000 }, async () => {
  const previousProject = process.env.TRIGGER_PROJECT_REF;
  process.env.TRIGGER_PROJECT_REF = 'proj_fixture';
  try {
    const { loadConfig } = await import(pathToFileURL(join(dirname(cliPackage), 'dist/esm/config.js')).href);
    const config = await loadConfig({ cwd: process.cwd(), warn: false });
    assert.equal(config.project, 'proj_fixture');
    assert.equal(config.runtime, 'node-24');
    assert.ok(config.dirs.includes('./src/trigger'));
    assert.ok(config.build.external.includes('playwright-core'));
  } finally {
    if (previousProject === undefined) delete process.env.TRIGGER_PROJECT_REF;
    else process.env.TRIGGER_PROJECT_REF = previousProject;
  }
});

test('the CLI template loader extracts an owned archive with patched tar', { timeout: 15_000 }, async () => {
  const root = await mkdtemp(join(tmpdir(), 'notte-trigger-cli-'));
  const previousCache = process.env.XDG_CACHE_HOME;
  process.env.XDG_CACHE_HOME = join(root, 'cache');
  const server = createServer();
  try {
    const tar = gigetRequire('tar');
    assert.equal(gigetRequire('tar/package.json').version, '7.5.22');
    const { downloadTemplate } = await import(pathToFileURL(gigetPath).href);
    await mkdir(join(root, 'archive', 'fixture-root', 'nested'), { recursive: true });
    await writeFile(join(root, 'archive', 'fixture-root', 'README.md'), 'owned fixture\n');
    await writeFile(join(root, 'archive', 'fixture-root', 'nested', 'page.txt'), 'nested\n');
    const archive = join(root, 'fixture.tar.gz');
    await tar.create({ cwd: join(root, 'archive'), file: archive, gzip: true }, ['fixture-root']);
    const content = await readFile(archive);
    server.on('request', (_request, response) => { response.end(content); });
    await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
    const address = server.address();
    assert.ok(address && typeof address !== 'string');
    await downloadTemplate('fixture:owned', {
      registry: false, auth: '', cwd: root, dir: 'result', silent: true,
      providers: { fixture: () => ({ name: 'owned', tar: `http://127.0.0.1:${address.port}/fixture.tar.gz` }) },
    });
    assert.equal(await readFile(join(root, 'result', 'README.md'), 'utf8'), 'owned fixture\n');
    assert.equal(await readFile(join(root, 'result', 'nested', 'page.txt'), 'utf8'), 'nested\n');
  } finally {
    await new Promise<void>(resolve => server.close(() => resolve()));
    if (previousCache === undefined) delete process.env.XDG_CACHE_HOME;
    else process.env.XDG_CACHE_HOME = previousCache;
    await rm(root, { recursive: true, force: true });
  }
});
