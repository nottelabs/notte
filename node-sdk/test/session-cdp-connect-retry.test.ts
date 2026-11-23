/** `session.page()` retries a CDP connection once when it drops before the WebSocket upgrade. Mirrors `tests/sdk/test_session_cdp_connect_retry.py`. */
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { chromium } from 'playwright-core';
import { Session } from '@/session';
import { sessionStart, sessionStatus } from '@/lib/client/sdk.gen';
import { mockNotteClient, sessionResponse } from './helpers/session-mocks';

vi.mock('@/lib/client/sdk.gen', () => ({
  sessionStart: vi.fn(),
  sessionStatus: vi.fn(),
}));

vi.mock('playwright-core', () => ({
  chromium: { connectOverCDP: vi.fn() },
}));

const CDP_URL = 'wss://notte.example/s/token';

// First lines and call logs as playwright-core 1.65 reports them.
const HANG_UP = new Error(
  'browserType.connectOverCDP: WebSocket error: socket hang up\nCall log:\n' +
    `  - <ws connect error> ${CDP_URL} socket hang up\n` +
    `  - <ws disconnected> ${CDP_URL} code=1006 reason=`,
);
const TRANSPORT_FAILURES = [
  HANG_UP,
  new Error('browserType.connectOverCDP: WebSocket error: read ECONNRESET'),
  new Error('browserType.connectOverCDP: WebSocket error: connect ECONNREFUSED 127.0.0.1:443'),
  new Error('browserType.connectOverCDP: WebSocket error: connect ETIMEDOUT 10.0.0.1:443'),
  new Error(
    'browserType.connectOverCDP: WebSocket error: Client network socket disconnected before secure TLS connection was established',
  ),
];

function httpAnswer(status: string, body: string): Error {
  return new Error(
    `browserType.connectOverCDP: WebSocket error: ${CDP_URL} ${status}\n${body}\nCall log:\n` +
      `  - <ws unexpected response> ${CDP_URL} ${status}\n` +
      `  - <ws connect error> ${CDP_URL} socket hang up\n` +
      `  - <ws disconnected> ${CDP_URL} code=1006 reason=`,
  );
}

const NOT_RETRIED = [
  httpAnswer('403 Forbidden', 'Session URL expired'),
  httpAnswer('403 Forbidden', 'InvalidRoutingToken'),
  httpAnswer('410 Gone', ''),
  httpAnswer('503 Service Unavailable', 'connection limit reached, ECONNREFUSED'),
  Object.assign(new Error('browserType.connectOverCDP: Timeout 30000ms exceeded.\nCall log:\n  - <ws connecting> wss://x'), {
    name: 'TimeoutError',
  }),
];

function browserWithPage() {
  const page = { goto: vi.fn() };
  const context = { on: vi.fn(), pages: () => [page] };
  return { browser: { contexts: () => [context], close: vi.fn(async () => {}) }, page };
}

async function startedSession(): Promise<Session> {
  const session = new Session(mockNotteClient());
  await session.start();
  return session;
}

const firstLine = (error: Error) => error.message.split('\n')[0];

describe('session.page() CDP connection retry', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse({ cdp_url: CDP_URL }) } as never);
    vi.mocked(sessionStatus).mockRejectedValue(new Error('status unavailable'));
  });

  it.each(TRANSPORT_FAILURES.map(error => [firstLine(error), error] as const))(
    'retries once after %s',
    async (_name, failure) => {
      const { browser, page } = browserWithPage();
      vi.mocked(chromium.connectOverCDP).mockRejectedValueOnce(failure).mockResolvedValueOnce(browser as never);
      const session = await startedSession();
      vi.mocked(console.warn).mockClear();

      expect(await session.page()).toBe(page);

      const calls = vi.mocked(chromium.connectOverCDP).mock.calls;
      expect(calls).toHaveLength(2);
      // The retry reuses the URL and the headers of the first attempt.
      expect(calls[1]).toEqual(calls[0]);
      expect(calls[1]?.[0]).toBe(CDP_URL);
      expect(console.warn).toHaveBeenCalledTimes(1);
      expect(String(vi.mocked(console.warn).mock.calls[0]?.[0])).not.toContain('token');
    },
  );

  it('retries only once', async () => {
    const { browser } = browserWithPage();
    vi.mocked(chromium.connectOverCDP)
      .mockRejectedValueOnce(HANG_UP)
      .mockRejectedValueOnce(HANG_UP)
      .mockResolvedValueOnce(browser as never);
    const session = await startedSession();

    const error = await session.page().catch((e: unknown) => e);

    expect(chromium.connectOverCDP).toHaveBeenCalledTimes(2);
    expect((error as Error).cause).toBe(HANG_UP);
  });

  it.each(NOT_RETRIED.map(error => [firstLine(error), error] as const))('does not retry %s', async (_name, failure) => {
    const { browser } = browserWithPage();
    vi.mocked(chromium.connectOverCDP).mockRejectedValueOnce(failure).mockResolvedValueOnce(browser as never);
    const session = await startedSession();
    vi.mocked(console.warn).mockClear();

    const error = await session.page().catch((e: unknown) => e);

    expect(chromium.connectOverCDP).toHaveBeenCalledTimes(1);
    expect((error as Error).message).toBe(`Failed to access the playwright page from CDP: ${failure.message}`);
    expect(console.warn).not.toHaveBeenCalled();
  });
});
