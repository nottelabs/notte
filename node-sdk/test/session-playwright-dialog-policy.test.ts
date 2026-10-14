/** `session.page()` connects over CDP and leaves native dialogs to the backend. Mirrors `tests/sdk/test_session_playwright_dialog_policy.py`. */
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { chromium } from 'playwright-core';
import { Session, installServerOwnedDialogPolicy, observeServerOwnedDialog } from '@/session';
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

function browserWithPage() {
  const page = { goto: vi.fn(), on: vi.fn(), url: () => 'about:blank', isClosed: () => false };
  const context = { on: vi.fn(), pages: () => [page] };
  const browser = { contexts: () => [context], close: vi.fn(async () => {}), on: vi.fn(), isConnected: () => true };
  return { browser, context, page };
}

describe('session.page()', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse({ cdp_url: 'ws://notte.example/cdp' }) } as never);
    vi.mocked(sessionStop).mockResolvedValue({ data: sessionResponse({ status: 'closed' }) } as never);
  });

  it('makes the backend the native dialog owner', async () => {
    const { browser, context, page } = browserWithPage();
    vi.mocked(chromium.connectOverCDP).mockResolvedValue(browser as never);
    const session = new Session(mockNotteClient());
    await session.start();

    expect(await session.page()).toBe(page);

    expect(chromium.connectOverCDP).toHaveBeenCalledWith('ws://notte.example/cdp', {
      headers: { 'x-notte-request-origin': REQUEST_ORIGIN, 'x-notte-sdk-version': SDK_VERSION },
    });
    expect(context.on).toHaveBeenCalledWith('dialog', observeServerOwnedDialog);
    expect(context.on.mock.calls.filter(([event]) => event === 'dialog')).toHaveLength(1);
    expect(observeServerOwnedDialog({} as never)).toBeUndefined();
  });

  it("sends nothing extra to a caller's own browser", async () => {
    const { browser } = browserWithPage();
    vi.mocked(chromium.connectOverCDP).mockResolvedValue(browser as never);
    const session = new Session(mockNotteClient(), { cdp_url: 'wss://other.example/cdp' });
    await session.start();

    await session.page();

    expect(chromium.connectOverCDP).toHaveBeenCalledWith('wss://other.example/cdp');
  });

  it('caches the connection and closes it on stop', async () => {
    const { browser, page } = browserWithPage();
    vi.mocked(chromium.connectOverCDP).mockResolvedValue(browser as never);
    const session = new Session(mockNotteClient());
    await session.start();

    expect(await session.page()).toBe(page);
    expect(await session.page()).toBe(page);
    expect(chromium.connectOverCDP).toHaveBeenCalledTimes(1);

    await session.stop();
    expect(browser.close).toHaveBeenCalledTimes(1);
    expect(sessionStop).toHaveBeenCalledTimes(1);
  });

  it('closes the connection when use() fails', async () => {
    const { browser } = browserWithPage();
    vi.mocked(chromium.connectOverCDP).mockResolvedValue(browser as never);
    vi.spyOn(console, 'error').mockImplementation(() => {});

    await expect(new Session(mockNotteClient()).use(async session => {
      await session.page();
      throw new Error('callback failed');
    })).rejects.toThrow('callback failed');

    expect(browser.close).toHaveBeenCalledTimes(1);
    expect(sessionStop).toHaveBeenCalledWith(expect.objectContaining({ query: { close_reason: 'error' } }));
  });

  it('wraps connection failures', async () => {
    vi.mocked(chromium.connectOverCDP).mockRejectedValue(new Error('ECONNREFUSED'));
    const session = new Session(mockNotteClient());
    await session.start();
    await expect(session.page()).rejects.toThrow('Failed to access the playwright page from CDP: ECONNREFUSED');
  });

  it('fails when the browser has no page', async () => {
    const browser = { contexts: () => [], close: vi.fn(), on: vi.fn(), isConnected: () => true };
    vi.mocked(chromium.connectOverCDP).mockResolvedValue(browser as never);
    const session = new Session(mockNotteClient());
    await session.start();
    await expect(session.page()).rejects.toThrow('the browser has no open page');
  });

  it('requires a started session', async () => {
    await expect(new Session(mockNotteClient()).page()).rejects.toThrow('Session not started');
    expect(chromium.connectOverCDP).not.toHaveBeenCalled();
  });

  it('installs the policy on every context', () => {
    const contexts = [{ on: vi.fn() }, { on: vi.fn() }];
    installServerOwnedDialogPolicy({ contexts: () => contexts } as never);
    for (const context of contexts) {
      expect(context.on).toHaveBeenCalledWith('dialog', observeServerOwnedDialog);
    }
  });
});
