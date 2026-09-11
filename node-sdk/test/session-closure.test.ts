import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { type NotteClient, sessionStatus } from '@/index';
import { expectSessionClosed } from './helpers/session-closure';

vi.mock('@/index', () => ({ sessionStatus: vi.fn() }));
const client = { getClient: () => ({}) } as NotteClient;
const status = (value: string) => ({ data: { status: value } }) as Awaited<ReturnType<typeof sessionStatus>>;

beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(sessionStatus).mockReset();
});
afterEach(() => vi.useRealTimers());

describe('session closure checks', () => {
  it('returns immediately when closure is already persisted', async () => {
    vi.mocked(sessionStatus).mockResolvedValue(status('closed'));
    await expectSessionClosed(client, 'owned-session', 'example (python)');
    expect(sessionStatus).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('waits through stale active reads and stops on the first closed response', async () => {
    vi.mocked(sessionStatus)
      .mockResolvedValueOnce(status('active'))
      .mockResolvedValueOnce(status('active'))
      .mockResolvedValueOnce(status('closed'));
    const check = expectSessionClosed(client, 'owned-session', 'example (python)');
    await vi.advanceTimersByTimeAsync(1000);
    await check;
    expect(sessionStatus).toHaveBeenCalledTimes(3);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('fails with resource, language and observations when closure never persists', async () => {
    vi.mocked(sessionStatus).mockResolvedValue(status('active'));
    const check = expectSessionClosed(client, 'owned-session', 'example (python)');
    const assertion = expect(check).rejects.toThrow(/example \(python\): session owned-session.*15000ms; observed 0ms=active/);
    await vi.advanceTimersByTimeAsync(15_000);
    await assertion;
    expect(sessionStatus).toHaveBeenCalledTimes(30);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('does not retry API failures', async () => {
    const error = new Error('Unauthorized');
    vi.mocked(sessionStatus).mockRejectedValue(error);
    await expect(expectSessionClosed(client, 'owned-session', 'example')).rejects.toBe(error);
    expect(sessionStatus).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('does not retry unexpected terminal statuses', async () => {
    vi.mocked(sessionStatus).mockResolvedValue(status('error'));
    await expect(expectSessionClosed(client, 'owned-session', 'example')).rejects.toThrow(
      'example: session owned-session returned unexpected status error',
    );
    expect(sessionStatus).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('aborts a status request that exceeds the polling deadline', async () => {
    vi.mocked(sessionStatus).mockImplementation(({ signal }) => new Promise<never>((_, reject) => {
      signal!.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
    }));
    const check = expectSessionClosed(client, 'owned-session', 'example');
    const assertion = expect(check).rejects.toThrow(/owned-session.*15000ms; observed no response/);
    await vi.advanceTimersByTimeAsync(15_000);
    await assertion;
    expect(sessionStatus).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });
});
