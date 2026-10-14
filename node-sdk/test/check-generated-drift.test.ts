import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { collectGeneratedDiffs, listFiles, resolveInside, run } = require('../scripts/check-generated-drift.js') as {
  collectGeneratedDiffs: (expectedSdkDir: string, actualSdkDir: string) => string[];
  listFiles: (rootPath: string) => string[];
  resolveInside: (baseDir: string, ...segments: string[]) => string;
  run: (command: string, args: string[]) => string;
};

describe('check-generated-drift', () => {
  let root: string;

  const write = (relativePath: string, content: string) => {
    const filePath = path.join(root, relativePath);
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content);
  };

  beforeEach(() => {
    root = fs.mkdtempSync(path.join(os.tmpdir(), 'drift-test-'));
  });

  afterEach(() => {
    fs.rmSync(root, { recursive: true, force: true });
  });

  describe('resolveInside', () => {
    it('resolves segments under the base directory', () => {
      expect(resolveInside(root, 'src', 'lib/client')).toBe(path.join(root, 'src', 'lib', 'client'));
      expect(resolveInside(root, '')).toBe(root);
      expect(resolveInside(root, '..foo')).toBe(path.join(root, '..foo'));
    });

    it.each(['..', '../x', 'a/../../x', '/etc/passwd'])('refuses %s, which escapes the base directory', (segment) => {
      expect(() => resolveInside(root, segment)).toThrow(/Path escapes/);
    });
  });

  describe('run', () => {
    it('refuses commands outside the allowlist', () => {
      expect(() => run('sh', ['-c', 'echo unexpected'])).toThrow('Refusing to run unexpected command: sh');
    });

    it('runs allowlisted commands', () => {
      expect(run('git', ['--version'])).toMatch(/^git version/);
    });
  });

  describe('listFiles', () => {
    it('lists nested files relative to the root, and a file root as itself', () => {
      write('dir/b.ts', 'b');
      write('dir/nested/a.ts', 'a');
      fs.symlinkSync('b.ts', path.join(root, 'dir', 'link.ts'));

      expect(listFiles(path.join(root, 'dir'))).toEqual(['b.ts', 'link.ts', path.join('nested', 'a.ts')]);
      expect(listFiles(path.join(root, 'dir', 'b.ts'))).toEqual(['']);
      expect(listFiles(path.join(root, 'missing'))).toEqual([]);
    });
  });

  describe('collectGeneratedDiffs', () => {
    it('reports added, removed, changed and relinked generated files only', () => {
      for (const side of ['expected', 'actual']) {
        write(`${side}/src/lib/client/same.ts`, 'same');
        write(`${side}/src/lib/client/nested/changed.ts`, side);
        write(`${side}/src/resources.gen.ts`, 'same');
        write(`${side}/src/not-generated.ts`, side);
      }
      write('expected/src/lib/client/only-expected.ts', 'x');
      write('actual/src/lib/client/nested/only-actual.ts', 'x');
      write('expected/src/proxy/patterns.ts', 'x');
      fs.symlinkSync('same.ts', path.join(root, 'expected/src/lib/client/link.ts'));
      fs.symlinkSync('other.ts', path.join(root, 'actual/src/lib/client/link.ts'));

      expect(collectGeneratedDiffs(path.join(root, 'expected'), path.join(root, 'actual'))).toEqual(
        [
          'src/lib/client/link.ts',
          'src/lib/client/nested/changed.ts',
          'src/lib/client/nested/only-actual.ts',
          'src/lib/client/only-expected.ts',
          'src/proxy/patterns.ts',
        ].map((file) => path.join(...file.split('/'))),
      );
    });
  });
});

// Exercise the real CLI in an isolated Git repo: the snapshot is outside node-sdk,
// runtime API overrides must not affect generation, and checks must not repair files.
describe('committed-snapshot generation', () => {
  it('checks offline and detects missing, stale and extra output without writing', () => {
    const sdkRoot = fileURLToPath(new URL('..', import.meta.url));
    const repoRoot = path.resolve(sdkRoot, '..');
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'snapshot-check-'));
    try {
      const files = execFileSync('git', ['ls-files', '-z', '--', 'node-sdk', 'openapi/openapi.json', 'openapi/resources.json'], { cwd: repoRoot, encoding: 'utf8' }).split('\0').filter(Boolean);
      for (const file of files) {
        const source = path.join(repoRoot, file);
        if (!fs.existsSync(source)) continue;
        const destination = path.join(root, file);
        fs.mkdirSync(path.dirname(destination), { recursive: true });
        fs.copyFileSync(source, destination);
      }
      execFileSync('git', ['init', '--quiet'], { cwd: root });
      execFileSync('git', ['add', '.'], { cwd: root });
      fs.symlinkSync(path.join(sdkRoot, 'node_modules'), path.join(root, 'node-sdk/node_modules'), 'dir');
      const check = () => spawnSync(process.execPath, ['scripts/check-generated-drift.js'], {
        cwd: path.join(root, 'node-sdk'), encoding: 'utf8',
        env: { ...process.env, NOTTE_API_URL: 'http://127.0.0.1:1' },
      });
      const clean = check();
      expect(clean.stdout + clean.stderr).toContain('up to date with the committed OpenAPI snapshot');
      expect(clean.status).toBe(0);

      const snapshot = path.join(root, 'openapi/openapi.json');
      const originalSpec = fs.readFileSync(snapshot, 'utf8');
      const modifiedSpec = JSON.parse(originalSpec);
      modifiedSpec.components.schemas.ProfileResponse.description = 'Changed snapshot description';
      fs.writeFileSync(snapshot, JSON.stringify(modifiedSpec));
      const changedSpec = check();
      expect(changedSpec.status).toBe(1);
      expect(changedSpec.stderr).toContain('src/lib/client/types.gen.ts');
      fs.writeFileSync(snapshot, originalSpec);

      const missing = path.join(root, 'node-sdk/src/proxy/patterns.ts');
      const stale = path.join(root, 'node-sdk/src/resources.gen.ts');
      const extra = path.join(root, 'node-sdk/src/lib/client/obsolete.gen.ts');
      fs.unlinkSync(missing);
      fs.writeFileSync(stale, '// stale output\n');
      fs.writeFileSync(extra, '// obsolete output\n');
      execFileSync('git', ['add', '.'], { cwd: path.join(root, 'node-sdk/src') });
      const dirty = check();
      expect(dirty.status).toBe(1);
      for (const file of ['src/proxy/patterns.ts', 'src/resources.gen.ts', 'src/lib/client/obsolete.gen.ts']) {
        expect(dirty.stderr).toContain(file);
      }
      expect(fs.existsSync(missing)).toBe(false);
      expect(fs.readFileSync(stale, 'utf8')).toBe('// stale output\n');
      expect(fs.readFileSync(extra, 'utf8')).toBe('// obsolete output\n');
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
  }, 30_000);
});
