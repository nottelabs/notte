/** Mirrors `tests/integration/sdk/test_cookies.py` plus the `cookie_file` session option. */
import { afterEach, beforeEach, describe, it, expect } from 'vitest';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { NotteClient } from '@/client';
import { actions } from '@/actions';
import type { Cookie } from '@/lib/client/types.gen';

import { config } from 'dotenv';
config();

const cookies: Cookie[] = [
  {
    name: 'sb-db-auth-token',
    value: 'base64-XFV',
    domain: 'console.notte.cc',
    path: '/',
    expires: 1904382506.913704,
    httpOnly: false,
    secure: false,
    sameSite: 'Lax',
  },
];

describe('Cookies Integration Tests', () => {
  let client: NotteClient;
  let tempDir: string;

  beforeEach(async () => {
    tempDir = await mkdtemp(join(tmpdir(), 'notte-cookies-'));
    const apiKey = process.env.NOTTE_API_KEY;
    if (!apiKey) {
      throw new Error('NOTTE_API_KEY environment variable is required for integration tests');
    }
    client = new NotteClient({ apiKey, baseUrl: process.env.NOTTE_API_URL || 'https://api.notte.cc' });
  });

  afterEach(async () => {
    await rm(tempDir, { recursive: true, force: true });
  });

  it('sets cookies from a file', async () => {
    const cookieFile = join(tempDir, 'cookies.json');
    await writeFile(cookieFile, JSON.stringify(cookies));

    await client.Session({ proxies: false, idle_timeout_minutes: 1 }).use(async session => {
      const response = await session.setCookiesFromFile(cookieFile);
      expect(response.success).toBe(true);
    });
  });

  it('gets cookies after navigation', { timeout: 60_000 }, async () => {
    await client.Session({ proxies: false, idle_timeout_minutes: 1 }).use(async session => {
      await session.execute(actions.goto({ url: 'https://www.ecosia.org' }));
      await session.observe();
      const retrieved = await session.getCookies();
      expect(retrieved.length).toBeGreaterThan(0);
    });
  });

  it('sets and gets cookies', async () => {
    await client.Session({ proxies: false, idle_timeout_minutes: 1 }).use(async session => {
      await session.setCookies(cookies);
      const retrieved = await session.getCookies();
      const found = retrieved.find(
        cookie => cookie.name === cookies[0].name && cookie.domain === cookies[0].domain && cookie.value === cookies[0].value,
      );
      expect(found).toBeDefined();
    });
  });

  it('loads the cookie_file on start and saves the session cookies on stop', async () => {
    const cookieFile = join(tempDir, 'cookies.json');
    await writeFile(cookieFile, JSON.stringify(cookies));

    await client.Session({ proxies: false, idle_timeout_minutes: 1, cookie_file: cookieFile }).use(async session => {
      const retrieved = await session.getCookies();
      expect(retrieved.some(cookie => cookie.name === cookies[0].name)).toBe(true);
    });

    const saved = JSON.parse(await readFile(cookieFile, 'utf-8')) as Cookie[];
    // the original entry plus the cookies read back from the session
    expect(saved.length).toBeGreaterThan(cookies.length);
    expect(saved[0]).toEqual(cookies[0]);
    expect(saved.slice(1).some(cookie => cookie.name === cookies[0].name)).toBe(true);
  });
});
