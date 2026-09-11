import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { EventEmitter } from 'node:events';
import { NotteClient } from '@/client';

const state = vi.hoisted(() => ({ urls: [] as string[], debug: vi.fn(), close: true, terminate: vi.fn() }));
vi.mock('@/lib/client/sdk.gen', () => ({
  agentStart: async () => ({ data: { agent_id: 'agent', session_id: 'session' } }),
  agentStatus: async () => ({ data: { agent_id: 'agent', session_id: 'session', status: 'closed', answer: 'done' } }),
  sessionDebugInfo: state.debug,
}));
vi.mock('ws', () => ({ default: class extends EventEmitter {
  static CLOSED = 3;
  readyState = 0;
  constructor(url: URL) {
    super();
    state.urls.push(String(url));
    if (state.close) queueMicrotask(() => this.emit('close'));
  }
  terminate() { state.terminate(); this.readyState = 3; this.emit('close'); }
} }));

beforeEach(() => {
  vi.useFakeTimers();
  state.urls.length = 0;
  state.close = true;
  state.terminate.mockClear();
  state.debug.mockResolvedValue({ data: { ws: { logs: 'wss://api.example/sessions/session/debug/logs?token=scoped-viewer-token' } } });
});
afterEach(() => vi.useRealTimers());

function run() {
  const client = new NotteClient({ baseUrl: 'https://api.example', apiKey: 'account-test-key' }); // pragma: allowlist secret
  const session = client.Session();
  vi.spyOn(session, 'getId').mockReturnValue('session');
  return client.Agent({ session }).run({ task: 'test' });
}

it('uses a scoped viewer token and clears the timer when logs close', async () => {
  await expect(run()).resolves.toMatchObject({ status: 'closed' });
  expect(state.urls).toHaveLength(1);
  expect(state.urls[0]).not.toContain('account-test-key');
  expect(new URL(state.urls[0]).searchParams.get('token')).toBe('scoped-viewer-token');
  expect(vi.getTimerCount()).toBe(0);
});

it.each(['wss://api.example/?token=account-test-key', 'ws://api.example/?token=scoped-viewer-token'])('polls instead of using unsafe URL %s', async url => {
  state.debug.mockResolvedValue({ data: { ws: { logs: url } } });
  await expect(run()).resolves.toMatchObject({ status: 'closed' });
  expect(state.urls).toEqual([]);
});

it('times out a socket that never opens and polls to completion', async () => {
  state.close = false;
  const result = run();
  await vi.advanceTimersByTimeAsync(300000);
  await expect(result).resolves.toMatchObject({ status: 'closed' });
  expect(state.terminate).toHaveBeenCalledOnce();
  expect(vi.getTimerCount()).toBe(0);
});
