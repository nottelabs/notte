/** `session.reconnect()` replaces a dropped CDP connection. Mirrors `tests/sdk/test_session_playwright_reconnect.py`. */
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { chromium } from 'playwright-core';
import { Session, observeServerOwnedDialog } from '@/session';
import { sessionStart, sessionStop } from '@/lib/client/sdk.gen';
import { REQUEST_ORIGIN } from '@/client';
import { SDK_VERSION } from '@/version';
import { mockNotteClient, sessionResponse } from './helpers/session-mocks';

vi.mock('@/lib/client/sdk.gen', () => ({
  sessionStart: vi.fn(),
  sessionStop: vi.fn(),
}));

vi.mock('playwright-core', () => ({
  chromium: { connectOverCDP: vi.fn() },
}));

const HEADERS = { 'x-notte-request-origin': REQUEST_ORIGIN, 'x-notte-sdk-version': SDK_VERSION };

function binding(connected = true) {
  const page = { goto: vi.fn() };
  const context = { on: vi.fn(), pages: () => [page] };
  const browser = {
    contexts: () => [context],
    isConnected: vi.fn(() => connected),
    close: vi.fn(async () => {}),
  };
  return { browser, context, page };
}

/** A started session whose `page()` connection has dropped. */
async function sessionWithDisconnectedPage(options = {}) {
  const old = binding(false);
  vi.mocked(chromium.connectOverCDP).mockResolvedValueOnce(old.browser as never);
  const session = new Session(mockNotteClient(), options);
  await session.start();
  expect(await session.page()).toBe(old.page);
  vi.mocked(chromium.connectOverCDP).mockClear();
  return { session, old };
}

describe('session.reconnect()', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse({ cdp_url: 'ws://notte.example/cdp' }) } as never);
    vi.mocked(sessionStop).mockResolvedValue({ data: sessionResponse({ status: 'closed' }) } as never);
  });

  it('replaces the binding without replaying actions or stopping the session', async () => {
    const { session, old } = await sessionWithDisconnectedPage();
    const fresh = binding();
    vi.mocked(chromium.connectOverCDP).mockResolvedValue(fresh.browser as never);

    expect(await session.reconnect({ timeout_ms: 1500 })).toBe(fresh.page);

    expect(chromium.connectOverCDP).toHaveBeenCalledExactlyOnceWith('ws://notte.example/cdp', {
      headers: HEADERS,
      timeout: 1500,
    });
    expect(fresh.context.on).toHaveBeenCalledExactlyOnceWith('dialog', observeServerOwnedDialog);
    expect(await session.page()).toBe(fresh.page);
    expect(old.browser.close).not.toHaveBeenCalled();
    expect(old.page.goto).not.toHaveBeenCalled();
    expect(fresh.page.goto).not.toHaveBeenCalled();
    expect(sessionStart).toHaveBeenCalledTimes(1);
    expect(sessionStop).not.toHaveBeenCalled();

    // A healthy connection is reused.
    expect(await session.reconnect()).toBe(fresh.page);
    expect(chromium.connectOverCDP).toHaveBeenCalledTimes(1);

    await session.stop();
    expect(fresh.browser.close).toHaveBeenCalledTimes(1);
  });

  it("sends nothing extra to a caller's own browser", async () => {
    const { session } = await sessionWithDisconnectedPage({ cdp_url: 'wss://other.example/cdp' });
    vi.mocked(chromium.connectOverCDP).mockResolvedValue(binding().browser as never);

    await session.reconnect();

    expect(chromium.connectOverCDP).toHaveBeenCalledExactlyOnceWith('wss://other.example/cdp', { timeout: 10_000 });
  });

  it('keeps the old binding after a failed handshake and can be attempted again', async () => {
    const { session, old } = await sessionWithDisconnectedPage();
    const fresh = binding();
    vi.mocked(chromium.connectOverCDP)
      .mockRejectedValueOnce(new Error('handshake failed'))
      .mockResolvedValueOnce(fresh.browser as never);

    await expect(session.reconnect()).rejects.toThrow('handshake failed');
    expect(await session.page()).toBe(old.page);
    expect(chromium.connectOverCDP).toHaveBeenCalledTimes(1);

    expect(await session.reconnect()).toBe(fresh.page);
  });

  it('closes a replacement that has no page and keeps the old binding', async () => {
    const { session, old } = await sessionWithDisconnectedPage();
    const empty = { contexts: () => [], close: vi.fn(async () => {}) };
    vi.mocked(chromium.connectOverCDP).mockResolvedValue(empty as never);

    await expect(session.reconnect()).rejects.toThrow('the browser has no open page');
    expect(empty.close).toHaveBeenCalledTimes(1);
    expect(await session.page()).toBe(old.page);
    expect(sessionStop).not.toHaveBeenCalled();
  });

  it('shares one attempt between concurrent calls', async () => {
    const { session } = await sessionWithDisconnectedPage();
    const fresh = binding();
    vi.mocked(chromium.connectOverCDP).mockImplementation(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
      return fresh.browser as never;
    });

    expect(await Promise.all([session.reconnect(), session.reconnect()])).toEqual([fresh.page, fresh.page]);
    expect(chromium.connectOverCDP).toHaveBeenCalledTimes(1);
  });

  it('discards a replacement when the session stops while reconnecting', async () => {
    const { session, old } = await sessionWithDisconnectedPage();
    const fresh = binding();
    let finish: (browser: unknown) => void = () => {};
    vi.mocked(chromium.connectOverCDP).mockReturnValue(new Promise(resolve => { finish = resolve; }) as never);

    const pending = session.reconnect();
    await vi.waitFor(() => expect(chromium.connectOverCDP).toHaveBeenCalled());
    await session.stop();
    finish(fresh.browser);

    await expect(pending).rejects.toThrow('the session was stopped while reconnecting');
    expect(old.browser.close).toHaveBeenCalledTimes(1);
    expect(fresh.browser.close).toHaveBeenCalledTimes(1);
  });

  it('does not share a stopped attempt with a restarted session', async () => {
    const { session } = await sessionWithDisconnectedPage();
    const stale = binding();
    let finish: (browser: unknown) => void = () => {};
    vi.mocked(chromium.connectOverCDP).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }) as never);

    const pending = session.reconnect();
    await vi.waitFor(() => expect(chromium.connectOverCDP).toHaveBeenCalled());
    await session.stop();

    const restarted = binding();
    vi.mocked(chromium.connectOverCDP).mockResolvedValueOnce(restarted.browser as never);
    await session.start();
    expect(await session.page()).toBe(restarted.page);
    expect(await session.reconnect()).toBe(restarted.page);

    finish(stale.browser);
    await expect(pending).rejects.toThrow('the session was stopped while reconnecting');
    expect(stale.browser.close).toHaveBeenCalledTimes(1);
    expect(await session.page()).toBe(restarted.page);
  });

  it.each([0, -1, Infinity, Number.NaN])('rejects timeout_ms=%s without connecting', async timeout => {
    const { session } = await sessionWithDisconnectedPage();
    await expect(session.reconnect({ timeout_ms: timeout })).rejects.toThrow(RangeError);
    expect(chromium.connectOverCDP).not.toHaveBeenCalled();
  });

  it('requires session.page() first', async () => {
    const session = new Session(mockNotteClient());
    await session.start();
    await expect(session.reconnect()).rejects.toThrow('Initialize session.page() before calling reconnect()');
    expect(chromium.connectOverCDP).not.toHaveBeenCalled();
  });
});
