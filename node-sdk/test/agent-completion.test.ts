import { afterEach, expect, it, vi } from 'vitest';
import { NotteClient } from '@/client';
import type { LegacyAgentStatusResponse } from '@/lib/client/types.gen';

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

it.each([false, true])('waits for terminal status when logs disconnect (throws=%s)', async throws => {
  vi.useFakeTimers();
  const client = new NotteClient({ baseUrl: '/api/notte' });
  const session = client.Session();
  vi.spyOn(session, 'getId').mockReturnValue('session');
  const agent = client.Agent({ session });
  vi.spyOn(agent, 'start').mockResolvedValue({ agent_id: 'agent', session_id: 'session' } as any);
  const logs = vi.spyOn(agent as any, 'watchLogs');
  if (throws) logs.mockRejectedValue(new Error('disconnected'));
  else logs.mockResolvedValue(null);
  const final = { agent_id: 'agent', session_id: 'session', status: 'closed', answer: 'done' } as LegacyAgentStatusResponse;
  vi.spyOn(agent, 'status').mockResolvedValueOnce({ ...final, status: 'active' }).mockResolvedValue(final);
  let settled = false;
  const result = agent.run({ task: 'test' }).then(value => { settled = true; return value; });
  await vi.advanceTimersByTimeAsync(0);
  expect(settled).toBe(false);
  await vi.advanceTimersByTimeAsync(3000);
  await expect(result).resolves.toEqual(final);
});

it('rejects a timed-out run rather than returning an active response', async () => {
  vi.useFakeTimers();
  const client = new NotteClient({ baseUrl: '/api/notte' });
  const session = client.Session();
  vi.spyOn(session, 'getId').mockReturnValue('session');
  const agent = client.Agent({ session });
  vi.spyOn(agent, 'start').mockResolvedValue({ agent_id: 'agent', session_id: 'session' } as any);
  vi.spyOn(agent, 'status').mockResolvedValue({ status: 'active' } as LegacyAgentStatusResponse);
  const result = expect(agent.run({ task: 'test' })).rejects.toThrow('polling timeout');
  await vi.advanceTimersByTimeAsync(300000);
  await result;
});
