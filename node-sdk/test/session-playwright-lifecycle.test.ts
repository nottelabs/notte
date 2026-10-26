/**
 * Playwright lifecycle diagnostics of `session.page()`. Mirrors the lifecycle
 * tests in `tests/sdk/test_session_playwright_dialog_policy.py`.
 */
import { EventEmitter } from 'node:events';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { chromium } from 'playwright-core';
import { Session, redactPlaywrightUrl } from '@/session';
import { sessionStart, sessionStop } from '@/lib/client/sdk.gen';
import type { NotteClientConfig } from '@/client';
import { mockNotteClient, sessionResponse } from './helpers/session-mocks';

vi.mock('@/lib/client/sdk.gen', () => ({
  sessionStart: vi.fn(),
  sessionStop: vi.fn(),
}));

vi.mock('playwright-core', () => ({
  chromium: { connectOverCDP: vi.fn() },
}));

class FakePage extends EventEmitter {
  closed = false;
  constructor(public href = 'about:blank') {
    super();
  }
  url = vi.fn(() => this.href);
  isClosed = vi.fn(() => this.closed);
  close(): void {
    this.closed = true;
    this.emit('close', this);
  }
}

class FakeContext extends EventEmitter {
  constructor(public openPages: FakePage[]) {
    super();
  }
  pages(): FakePage[] {
    return this.openPages.filter(page => !page.closed);
  }
  newPage(): FakePage {
    const page = new FakePage();
    this.openPages.push(page);
    this.emit('page', page);
    return page;
  }
}

class FakeBrowser extends EventEmitter {
  connected = true;
  constructor(public context: FakeContext) {
    super();
  }
  contexts(): FakeContext[] {
    return [this.context];
  }
  isConnected(): boolean {
    return this.connected;
  }
  close = vi.fn(async () => {
    for (const page of this.context.pages()) page.close();
    this.context.emit('close', this.context);
    this.disconnect();
  });
  disconnect(): void {
    this.connected = false;
    this.emit('disconnected', this);
  }
}

function fakeBrowser(url = 'https://example.com/') {
  const page = new FakePage(url);
  const context = new FakeContext([page]);
  return { browser: new FakeBrowser(context), context, page };
}

type Captured = { level: string; event: string; message: string };
let captured: Captured[];

function events(): Array<[string, string]> {
  return captured.map(({ level, event }) => [level, event]);
}

async function connectedSession(config: NotteClientConfig = { logLevel: 'debug' }, url?: string) {
  const fake = fakeBrowser(url);
  vi.mocked(chromium.connectOverCDP).mockResolvedValue(fake.browser as never);
  const session = new Session(mockNotteClient(config));
  await session.start();
  expect(await session.page()).toBe(fake.page);
  return { session, ...fake };
}

describe('session.page() lifecycle diagnostics', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.unstubAllEnvs();
    captured = [];
    for (const level of ['debug', 'info', 'warn', 'error'] as const) {
      vi.spyOn(console, level).mockImplementation((message?: unknown) => {
        const text = String(message);
        const match = /^\[Session Playwright\] (\w+):/.exec(text);
        if (match) captured.push({ level, event: match[1], message: text });
      });
    }
    vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse({ cdp_url: 'ws://notte.example/cdp' }) } as never);
    vi.mocked(sessionStop).mockResolvedValue({ data: sessionResponse({ status: 'closed' }) } as never);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it('registers lifecycle listeners on the connection', async () => {
    const { browser, context, page } = await connectedSession();

    expect(browser.listenerCount('disconnected')).toBe(1);
    expect(context.listenerCount('page')).toBe(1);
    expect(context.listenerCount('close')).toBe(1);
    expect(page.listenerCount('close')).toBe(1);
    expect(page.listenerCount('crash')).toBe(1);
    expect(events()).toEqual([['info', 'sdk_playwright_connected']]);
  });

  it('logs every lifecycle callback with the connection state', async () => {
    const { browser, context, page } = await connectedSession();

    page.emit('crash', page);
    page.close();
    context.emit('close', context);
    browser.disconnect();

    expect(events()).toEqual([
      ['info', 'sdk_playwright_connected'],
      ['warn', 'sdk_playwright_page_crashed'],
      ['warn', 'sdk_playwright_page_closed'],
      ['warn', 'sdk_playwright_context_closed'],
      ['warn', 'sdk_playwright_browser_disconnected'],
    ]);
    const state = JSON.parse(captured.at(-1)!.message.split(' state=')[1]);
    expect(state).toMatchObject({
      connection_generation: 1,
      cleanup_in_progress: false,
      browser_connected: false,
      contexts: [{ pages: [], contains_cached_page: false }],
    });
    expect(captured.at(-1)!.message).toContain('session=session-123');
  });

  it('instruments new tabs and logs only the cached page close as a warning', async () => {
    const { context, page } = await connectedSession();

    const popup = context.newPage();
    expect(popup.listenerCount('close')).toBe(1);
    expect(popup.listenerCount('crash')).toBe(1);
    popup.close();
    page.close();

    expect(events()).toEqual([
      ['info', 'sdk_playwright_connected'],
      ['info', 'sdk_playwright_page_created'],
      ['info', 'sdk_playwright_page_closed'],
      ['warn', 'sdk_playwright_page_closed'],
    ]);
  });

  it('warns when the cached page is no longer live', async () => {
    const { session, page, browser } = await connectedSession();
    expect(await session.page()).toBe(page);
    expect(events()).toEqual([['info', 'sdk_playwright_connected']]);

    page.closed = true;
    expect(await session.page()).toBe(page);
    page.closed = false;
    browser.connected = false;
    expect(await session.page()).toBe(page);

    expect(events().slice(1)).toEqual([
      ['warn', 'sdk_playwright_cached_page_unhealthy'],
      ['warn', 'sdk_playwright_cached_page_unhealthy'],
    ]);
  });

  it.each([false, true])('reports the missing cached page closed state (%s)', async closed => {
    const { session, page, context, browser } = await connectedSession();
    page.closed = closed;
    context.openPages = [];
    browser.connected = false;

    expect(await session.page()).toBe(page);

    const state = JSON.parse(captured.at(-1)!.message.split(' state=')[1]);
    expect(state.contexts[0].contains_cached_page).toBe(false);
    expect(state.cached_page).toEqual({
      page_id: state.cached_page_id,
      is_closed: closed,
      url: 'https://example.com',
    });
  });

  it('never logs URL credentials, paths, queries or fragments', async () => {
    const { browser } = await connectedSession(
      { logLevel: 'debug' },
      'https://user:pass@example.com/callback?code=secret-code#access_token=secret-token', // pragma: allowlist secret
    );
    browser.disconnect();

    expect(captured.at(-1)!.message).toContain('"url":"https://example.com"');
    expect(captured.some(({ message }) => /secret|pass|user/.test(message))).toBe(false);
  });

  it.each([
    ['https://user@example.com:8443/cb?code=secret#token=secret', 'https://example.com:8443'],
    ['http://example.com/path-secret-token', 'http://example.com'],
    ['wss://example.com/ws?token=secret', 'wss://example.com'],
    ['file:///tmp/page-secret-token.html?x=secret', 'file:'],
    ['about:blank', 'about:blank'],
    ['about:blank?code=secret#token=secret', 'about:blank'],
    ['about:srcdoc#secret', 'about:srcdoc'],
    ['about:custom-secret', 'about:'],
    ['data:text/html,<p>secret</p>', 'data:'],
    ['javascript:alert(1)', 'javascript:'],
    ['', '<redacted>'],
    ['not a url', '<redacted>'],
    ['http://[bad', '<unparseable>'],
  ])('redacts %s', (url, expected) => {
    expect(redactPlaywrightUrl(url)).toBe(expected);
  });

  it("logs closes caused by the SDK's own cleanup at debug, after a stop snapshot at info", async () => {
    const { session, browser } = await connectedSession();
    let loggedBeforeClose: Array<[string, string]> = [];
    browser.close.mockImplementationOnce(async () => {
      loggedBeforeClose = events();
      browser.disconnect();
    });
    captured = [];

    await session.stop();

    expect(loggedBeforeClose).toEqual([['info', 'sdk_playwright_session_stop_requested']]);
    expect(events()).toEqual([
      ['info', 'sdk_playwright_session_stop_requested'],
      ['debug', 'sdk_playwright_browser_disconnected'],
    ]);
    expect(browser.close).toHaveBeenCalledTimes(1);
  });

  it('keeps the cached page identity while the SDK closes the browser', async () => {
    const { session, page } = await connectedSession();
    captured = [];

    await session.stop();

    const closed = captured.find(({ event }) => event === 'sdk_playwright_page_closed')!;
    expect(closed.level).toBe('debug');
    expect(JSON.parse(closed.message.split(' state=')[1]).cached_page_id).toBe(
      JSON.parse(closed.message.split(' state=')[1]).observed_page.page_id,
    );
    expect(page.closed).toBe(true);
  });

  it('keeps reporting failures as warnings when stop() fails', async () => {
    const { session, browser } = await connectedSession();
    vi.mocked(sessionStop).mockRejectedValueOnce(new Error('network down'));
    browser.close.mockImplementationOnce(async () => {});

    await expect(session.stop()).rejects.toThrow('network down');
    browser.disconnect();

    expect(events().at(-1)).toEqual(['warn', 'sdk_playwright_browser_disconnected']);
  });

  it('treats an already stopped session as cleanup', async () => {
    const { session, browser } = await connectedSession();
    vi.mocked(sessionStop).mockRejectedValueOnce(new Error('Session already stopped'));
    browser.close.mockImplementationOnce(async () => {});

    await session.stop();
    browser.disconnect();

    expect(events().at(-1)).toEqual(['debug', 'sdk_playwright_browser_disconnected']);
  });

  it('reports failures as warnings again after a restart', async () => {
    const { session } = await connectedSession();
    await session.stop();
    const next = fakeBrowser();
    vi.mocked(chromium.connectOverCDP).mockResolvedValue(next.browser as never);

    await session.start();
    await session.page();
    next.browser.disconnect();

    expect(events().at(-1)).toEqual(['warn', 'sdk_playwright_browser_disconnected']);
    expect(JSON.parse(captured.at(-1)!.message.split(' state=')[1]).connection_generation).toBe(2);
  });

  it('prints nothing for a normal use() lifecycle at the default level', async () => {
    const fake = fakeBrowser();
    vi.mocked(chromium.connectOverCDP).mockResolvedValue(fake.browser as never);

    await new Session(mockNotteClient()).use(async session => {
      const page = await session.page();
      expect(await session.page()).toBe(page);
      fake.context.newPage().close();
    });

    expect(fake.browser.close).toHaveBeenCalledTimes(1);
    expect(captured).toEqual([]);
  });

  it('honours NOTTE_LOG_LEVEL when the client sets no level', async () => {
    vi.stubEnv('NOTTE_LOG_LEVEL', 'info');
    await connectedSession({});
    expect(events()).toEqual([['info', 'sdk_playwright_connected']]);
  });

  it('builds no state snapshot for a disabled level', async () => {
    const { page, browser } = await connectedSession({ logLevel: 'silent' });
    page.url.mockClear();

    page.close();
    browser.disconnect();

    expect(captured).toEqual([]);
    expect(page.url).not.toHaveBeenCalled();
  });
});
