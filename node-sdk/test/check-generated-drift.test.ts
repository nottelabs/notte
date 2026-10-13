import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
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
