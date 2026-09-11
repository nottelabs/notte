/** Mirrors `tests/integration/sdk/test_cdp.py`: CDP connection and the server-owned dialog policy. */
import { afterEach, beforeEach, describe, it, expect } from 'vitest';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { chromium } from 'playwright-core';
import { NotteClient } from '@/client';
import { actions } from '@/actions';

import { config } from 'dotenv';
config();

describe('CDP Integration Tests', () => {
  let client: NotteClient;
  let tempDir: string;

  beforeEach(async () => {
    tempDir = await mkdtemp(join(tmpdir(), 'notte-cdp-'));
    const apiKey = process.env.NOTTE_API_KEY;
    if (!apiKey) {
      throw new Error('NOTTE_API_KEY environment variable is required for integration tests');
    }
    client = new NotteClient({ apiKey, baseUrl: process.env.NOTTE_API_URL || 'https://api.notte.cc' });
  });

  afterEach(async () => {
    await rm(tempDir, { recursive: true, force: true });
  });

  it('connects over CDP with cdpUrl()', { timeout: 90_000 }, async () => {
    await client.Session({ proxies: false }).use(async session => {
      const cdpUrl = await session.cdpUrl();
      expect(cdpUrl).toMatch(/^wss?:\/\//);

      const browser = await chromium.connectOverCDP(cdpUrl);
      try {
        const page = browser.contexts()[0].pages()[0];
        await page.goto('https://www.google.com');
        const path = join(tempDir, 'screenshot.png');
        await page.screenshot({ path });
        const png = await readFile(path);
        expect(png.subarray(0, 8)).toEqual(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
      } finally {
        await browser.close();
      }
    });
  });

  it('session.page() leaves native dialogs to the backend', { timeout: 90_000 }, async () => {
    await client.Session({ proxies: false }).use(async session => {
      const page = await session.page();
      expect(await session.page()).toBe(page);
      await page.goto('https://example.com');
      await page.evaluate("window.onbeforeunload = () => 'leave?'");

      const result = await session.execute(actions.goto({ url: 'https://example.org' }), { raiseOnFailure: true });

      await page.waitForURL('https://example.org/**');
      expect(result.success).toBe(true);
      expect(await page.title()).toBe('Example Domain');
    });
  });
});
