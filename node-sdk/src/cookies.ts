/**
 * Cookie file helpers, the counterpart of `SetCookiesRequest.from_json` and
 * `notte_core.common.config.create_or_append_cookies_to_file` in Python.
 */
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import type { Cookie } from '@/lib/client/types.gen';
import { InvalidRequestError } from '@/errors';

/** Read a JSON cookie file (a list of cookies, like `session.getCookies()` returns). */
export async function readCookiesFile(cookieFile: string): Promise<Cookie[]> {
  const cookies: unknown = JSON.parse(await readFile(cookieFile, 'utf-8'));
  if (!Array.isArray(cookies)) {
    throw new InvalidRequestError(`Cookie file ${cookieFile} must contain a JSON list of cookies`);
  }
  return cookies as Cookie[];
}

/**
 * Merge `cookies` into the JSON list stored in `cookieFile`, one entry per
 * cookie, creating the file when it does not exist yet.
 *
 * Sessions load the file when they start, so the browser's jar on stop repeats
 * the cookies it loaded: appending them blindly duplicated the whole file on
 * every stop. Merging (rather than overwriting) keeps cookies another session
 * saved to the same file. A cookie is identified by name, domain, path and
 * partition key; the newest value wins.
 */
export async function createOrAppendCookiesToFile(cookieFile: string, cookies: Cookie[]): Promise<void> {
  console.info(`🍪 Automatically saving cookies to ${cookieFile}`);
  // Sessions sharing one cookie file (stopped concurrently) must not read the
  // same contents and overwrite each other, so the read-modify-write runs
  // under a per-path lock. The lock is per process; a file shared between
  // processes still needs an external lock.
  await withFileLock(cookieFile, async () => {
    let existing: Cookie[] = [];
    try {
      existing = await readCookiesFile(cookieFile);
    } catch (error) {
      if (!isNotFound(error)) {
        throw error;
      }
    }
    const merged = new Map<string, Cookie>();
    for (const cookie of [...existing, ...cookies]) {
      merged.set(cookieIdentity(cookie), cookie);
    }
    await writeFile(cookieFile, JSON.stringify([...merged.values()]), 'utf-8');
  });
}

function cookieIdentity(cookie: Cookie): string {
  return JSON.stringify([cookie.name, cookie.domain ?? null, cookie.path ?? null, cookie.partitionKey ?? null]);
}

const fileLocks = new Map<string, Promise<void>>();

/** Run `fn` after every earlier operation queued for the same resolved path. */
async function withFileLock<T>(path: string, fn: () => Promise<T>): Promise<T> {
  const key = resolve(path);
  const previous = fileLocks.get(key) ?? Promise.resolve();
  let release!: () => void;
  const current = new Promise<void>(done => {
    release = done;
  });
  const tail = previous.then(() => current);
  fileLocks.set(key, tail);
  await previous;
  try {
    return await fn();
  } finally {
    release();
    // Evict the entry when nobody queued behind us, so paths used once do not
    // accumulate in long-running processes.
    if (fileLocks.get(key) === tail) {
      fileLocks.delete(key);
    }
  }
}

/** Test hook: number of cookie files with an in-flight or queued update. */
export function pendingCookieFileLocks(): number {
  return fileLocks.size;
}

function isNotFound(error: unknown): boolean {
  return typeof error === 'object' && error !== null && (error as { code?: string }).code === 'ENOENT';
}
