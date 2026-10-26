/**
 * Playwright lifecycle diagnostics against a real Chromium reached over CDP.
 * Mirrors `tests/integration/test_sdk_playwright_lifecycle.py`; needs no
 * credentials, only `npx playwright-core install chromium`.
 */
import { spawn, type ChildProcess } from 'node:child_process';
import { once } from 'node:events';
import { existsSync } from 'node:fs';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { chromium } from 'playwright-core';
import { Session } from '@/session';
import { sessionStart, sessionStop } from '@/lib/client/sdk.gen';
import type { NotteClientConfig } from '@/client';
import { mockNotteClient, sessionResponse } from './helpers/session-mocks';

vi.mock('@/lib/client/sdk.gen', () => ({
  sessionStart: vi.fn(),
  sessionStop: vi.fn(),
}));

const executable = chromium.executablePath();
// CI installs Chromium, so a missing browser there is a failure rather than a skip.
const runnable = existsSync(executable) || Boolean(process.env.CI);

async function freePort(): Promise<number> {
  const server = createServer();
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  await new Promise(resolve => server.close(resolve));
  if (address === null || typeof address === 'string') throw new Error('no port');
  return address.port;
}

async function waitForCdp(cdpUrl: string, browser: ChildProcess): Promise<void> {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (browser.exitCode !== null) break;
    try {
      if ((await fetch(`${cdpUrl}/json/version`)).ok) return;
    } catch {
      // Not listening yet.
    }
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  throw new Error('Chromium did not expose its CDP endpoint');
}

type Captured = [level: string, event: string, message: string];

describe.runIf(runnable)('session.page() lifecycle against a real browser', () => {
  let dir: string;
  let cdpUrl: string;
  let browserProcess: ChildProcess;
  let captured: Captured[];

  const events = () => captured.map(([level, event]) => [level, event]);
  const newSession = (config: NotteClientConfig) => new Session(mockNotteClient(config), { cdp_url: cdpUrl });

  // A fresh Chromium per test, like the Python `cdp_browser` fixture.
  beforeEach(async () => {
    dir = await mkdtemp(join(tmpdir(), 'notte-lifecycle-'));
    const port = await freePort();
    browserProcess = spawn(executable, [
      '--headless=new',
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${join(dir, 'profile')}`,
      '--no-first-run',
      '--no-default-browser-check',
      '--no-sandbox',
      '--disable-dev-shm-usage',
      'about:blank',
    ], { stdio: 'ignore' });
    cdpUrl = `http://127.0.0.1:${port}`;
    await waitForCdp(cdpUrl, browserProcess);
  }, 60_000);

  afterEach(async () => {
    if (browserProcess.exitCode === null) {
      const exited = once(browserProcess, 'exit');
      browserProcess.kill();
      await exited;
    }
    // Chromium helper processes can still be flushing the profile right after exit.
    await rm(dir, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  });

  beforeEach(() => {
    vi.resetAllMocks();
    captured = [];
    for (const level of ['debug', 'info', 'warn', 'error'] as const) {
      vi.spyOn(console, level).mockImplementation((message?: unknown) => {
        const text = String(message);
        const match = /^\[Session Playwright\] (\w+):/.exec(text);
        if (match) captured.push([level, match[1], text]);
      });
    }
    vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse({ session_id: 'local-session' }) } as never);
    vi.mocked(sessionStop).mockResolvedValue({ data: sessionResponse({ session_id: 'local-session', status: 'closed' }) } as never);
  });

  it('logs connection, tab and cleanup events without URL secrets', { timeout: 60_000 }, async () => {
    const html = join(dir, 'page.html');
    await writeFile(html, '<title>lifecycle</title>');
    const pageUrl = pathToFileURL(html).href;
    const session = newSession({ logLevel: 'debug' });
    await session.start();

    const page = await session.page();
    await page.goto(`${pageUrl}?token=secret-token#access_token=secret-fragment`);
    expect(events()).toEqual([['info', 'sdk_playwright_connected']]);

    const popup = await page.context().newPage();
    await popup.close();
    expect(await session.page()).toBe(page);
    await expect.poll(() => events().slice(1)).toEqual([
      ['info', 'sdk_playwright_page_created'],
      ['info', 'sdk_playwright_page_closed'],
    ]);

    await page.close();
    expect(await session.page()).toBe(page);
    expect(events().slice(3)).toEqual([
      ['warn', 'sdk_playwright_page_closed'],
      ['warn', 'sdk_playwright_cached_page_unhealthy'],
    ]);

    const cleanupPopup = await page.context().newPage();
    vi.mocked(sessionStop).mockImplementationOnce(async () => {
      await cleanupPopup.close();
      return { data: sessionResponse({ session_id: 'local-session', status: 'closed' }) } as never;
    });
    const beforeStop = captured.length;
    await session.stop();
    const cleanup = events().slice(beforeStop);
    expect(cleanup[0]).toEqual(['info', 'sdk_playwright_session_stop_requested']);
    expect(cleanup.slice(1)).toContainEqual(['debug', 'sdk_playwright_page_closed']);
    expect(cleanup.slice(1)).toContainEqual(['debug', 'sdk_playwright_browser_disconnected']);
    expect(cleanup.slice(1).every(([level]) => level === 'debug')).toBe(true);
    expect(sessionStop).toHaveBeenCalledTimes(1);

    const messages = captured.map(([, , message]) => message);
    expect(messages.some(message => message.includes('"url":"file:"'))).toBe(true);
    expect(messages.some(message => message.includes(pageUrl))).toBe(false);
    expect(messages.some(message => message.includes('secret'))).toBe(false);
  });

  it('prints nothing for a normal use() lifecycle at the default level', { timeout: 60_000 }, async () => {
    await newSession({}).use(async session => {
      const page = await session.page();
      await page.goto('about:blank');
      const popup = await page.context().newPage();
      await popup.close();
      expect(await session.page()).toBe(page);
    });

    expect(sessionStop).toHaveBeenCalledTimes(1);
    expect(captured).toEqual([]);
  });
});
