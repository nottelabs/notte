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

  it('connects over CDP with cdpUrl()', async () => {
    await client.Session({ proxies: false }).use(async session => {
      const cdpUrl = await session.cdpUrl();
      expect(cdpUrl).toMatch(/^wss?:\/\//);

      const browser = await chromium.connectOverCDP(cdpUrl);
      try {
        const page = browser.contexts()[0].pages()[0];
        const fixtureUrl = 'https://cdp-fixture.notte.test/';
        await page.route(fixtureUrl, route => route.fulfill({
          status: 200,
          contentType: 'text/html',
          body: '<!doctype html><title>CDP fixture</title><h1>Connected over CDP</h1>',
        }));
        const response = await page.goto(fixtureUrl);
        expect(response?.status()).toBe(200);
        expect(page.url()).toBe(fixtureUrl);
        expect(await page.title()).toBe('CDP fixture');
        expect(await page.locator('h1').innerText()).toBe('Connected over CDP');
        const path = join(tempDir, 'screenshot.png');
        await page.screenshot({ path });
        const png = await readFile(path);
        expect(png.subarray(0, 8)).toEqual(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
      } finally {
        await browser.close();
      }
    });
  });

  it('session.page() leaves native dialogs to the backend', async () => {
    await client.Session({ proxies: false }).use(async session => {
      const page = await session.page();
      expect(await session.page()).toBe(page);
      const firstUrl = 'https://cdp-fixture.notte.test/first';
      const nextUrl = 'https://cdp-fixture.notte.test/next';
      await page.route('https://cdp-fixture.notte.test/**', route => route.fulfill({
        status: 200,
        contentType: 'text/html',
        body: '<!doctype html><title>Dialog fixture</title><h1>Navigation completed</h1>',
      }));
      await page.goto(firstUrl);
      await page.evaluate("window.onbeforeunload = () => 'leave?'");

      const result = await session.execute(actions.goto({ url: nextUrl }), { raiseOnFailure: true });

      await page.waitForURL(nextUrl);
      expect(result.success).toBe(true);
      expect(await page.title()).toBe('Dialog fixture');
    });
  });
});
