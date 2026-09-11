/**
 * Cookie file helpers, the counterpart of `SetCookiesRequest.from_json` and
 * `notte_core.utils.files.create_or_append_cookies_to_file` in Python.
 */
import { readFile, writeFile } from 'node:fs/promises';
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
 * Append `cookies` to the JSON list stored in `cookieFile`, creating the file
 * when it does not exist yet.
 */
export async function createOrAppendCookiesToFile(cookieFile: string, cookies: Cookie[]): Promise<void> {
  console.info(`🍪 Automatically saving cookies to ${cookieFile}`);
  let existing: Cookie[] = [];
  try {
    existing = await readCookiesFile(cookieFile);
  } catch (error) {
    if (!isNotFound(error)) {
      throw error;
    }
  }
  existing.push(...cookies);
  await writeFile(cookieFile, JSON.stringify(existing), 'utf-8');
}

function isNotFound(error: unknown): boolean {
  return typeof error === 'object' && error !== null && (error as { code?: string }).code === 'ENOENT';
}
