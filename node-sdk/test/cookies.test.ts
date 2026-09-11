/**
 * Cookie file helpers: concurrent appends to one file must not lose writes.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { Cookie } from '@/lib/client/types.gen';
import { InvalidRequestError } from '@/errors';
import { createOrAppendCookiesToFile, readCookiesFile } from '@/cookies';

const cookie = (name: string): Cookie => ({ name, value: 'v', domain: 'example.com', path: '/', httpOnly: false });

describe('cookie files', () => {
  let dir: string;

  beforeEach(async () => {
    dir = await mkdtemp(join(tmpdir(), 'notte-cookie-test-'));
    vi.spyOn(console, 'info').mockImplementation(() => undefined);
  });

  afterEach(async () => {
    vi.restoreAllMocks();
    await rm(dir, { recursive: true, force: true });
  });

  it('rejects a file that is not a JSON list', async () => {
    const file = join(dir, 'bad.json');
    await writeFile(file, '{"name": "x"}');
    await expect(readCookiesFile(file)).rejects.toBeInstanceOf(InvalidRequestError);
  });

  it('creates the file when missing and appends afterwards', async () => {
    const file = join(dir, 'cookies.json');
    await createOrAppendCookiesToFile(file, [cookie('a')]);
    await createOrAppendCookiesToFile(file, [cookie('b')]);
    expect((await readCookiesFile(file)).map(c => c.name)).toEqual(['a', 'b']);
  });

  it('serialises concurrent appends to the same file so no write is lost', async () => {
    const file = join(dir, 'shared.json');
    const names = Array.from({ length: 25 }, (_, i) => `c${i}`);

    await Promise.all(names.map(name => createOrAppendCookiesToFile(file, [cookie(name)])));

    const saved = JSON.parse(await readFile(file, 'utf-8')) as Cookie[];
    expect(saved.map(c => c.name).sort()).toEqual([...names].sort());
  });

  it('locks per resolved path, so different files proceed independently', async () => {
    const a = join(dir, 'a.json');
    const b = join(dir, 'b.json');
    await Promise.all([createOrAppendCookiesToFile(a, [cookie('a')]), createOrAppendCookiesToFile(b, [cookie('b')])]);
    expect((await readCookiesFile(a)).map(c => c.name)).toEqual(['a']);
    expect((await readCookiesFile(b)).map(c => c.name)).toEqual(['b']);
  });
});
