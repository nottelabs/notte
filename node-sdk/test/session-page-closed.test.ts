/** `session.page()` explains a failed connection with the session's close reason. Mirrors `tests/sdk/test_session_page_closed.py`. */
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { chromium } from 'playwright-core';
import { Session } from '@/session';
import { SessionClosedError } from '@/errors';
import { sessionStart, sessionStatus } from '@/lib/client/sdk.gen';
import { mockNotteClient, sessionResponse } from './helpers/session-mocks';

vi.mock('@/lib/client/sdk.gen', () => ({
  sessionStart: vi.fn(),
  sessionStatus: vi.fn(),
}));

vi.mock('playwright-core', () => ({
  chromium: { connectOverCDP: vi.fn() },
}));

const REFUSED = new Error('WebSocket error: wss://notte.example/cdp 410 Gone');

async function startedSession(): Promise<Session> {
  const session = new Session(mockNotteClient());
  await session.start();
  return session;
}

describe('session.page() of a closed session', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse({ cdp_url: 'ws://notte.example/cdp' }) } as never);
    vi.mocked(chromium.connectOverCDP).mockRejectedValue(REFUSED);
  });

  it.each([
    ['timed_out', 'idle_timeout', 'Session session-1 is closed: it timed out after 6 minutes without activity.'],
    ['closed', 'max_duration', 'Session session-1 is closed: it reached its maximum duration of 15 minutes.'],
    ['closed', 'manual', 'Session session-1 is closed: it was stopped.'],
    ['error', null, 'Session session-1 is closed: its status is error.'],
  ] as const)('throws SessionClosedError when the session is %s (%s)', async (status, closeReason, message) => {
    vi.mocked(sessionStatus).mockResolvedValue({
      data: sessionResponse({
        session_id: 'session-1',
        status,
        close_reason: closeReason,
        idle_timeout_minutes: 6,
        max_duration_minutes: 15,
      }),
    } as never);
    const session = await startedSession();

    const error = await session.page().catch((e: unknown) => e);

    expect(error).toBeInstanceOf(SessionClosedError);
    expect((error as SessionClosedError).message.startsWith(message)).toBe(true);
    expect((error as SessionClosedError).closeReason).toBe(closeReason);
    expect((error as SessionClosedError).cause).toBe(REFUSED);
  });

  it.each([
    ['active', () => vi.mocked(sessionStatus).mockResolvedValue({ data: sessionResponse({ status: 'active' }) } as never)],
    ['paused', () => vi.mocked(sessionStatus).mockResolvedValue({ data: sessionResponse({ status: 'paused' }) } as never)],
    ['status unavailable', () => vi.mocked(sessionStatus).mockRejectedValue(new Error('status unavailable'))],
  ])('keeps the connection error when the session is %s', async (_name, mockStatus) => {
    mockStatus();
    const session = await startedSession();

    const error = await session.page().catch((e: unknown) => e);

    expect(error).not.toBeInstanceOf(SessionClosedError);
    expect((error as Error).message).toBe(`Failed to access the playwright page from CDP: ${REFUSED.message}`);
  });
});
