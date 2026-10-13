import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { NotteClient } from '@/client';

const mocks = vi.hoisted(() => ({
  getUsage: vi.fn(),
  getUsageLogs: vi.fn(),
}));

vi.mock('@/lib/client/sdk.gen', () => mocks);

import { NotteUsage } from '@/usage';

describe('NotteUsage', () => {
  const generated = { id: 'test-client' };
  const client = { getClient: () => generated } as unknown as NotteClient;
  let usage: NotteUsage;

  beforeEach(() => {
    Object.values(mocks).forEach(mock => mock.mockReset());
    usage = new NotteUsage(client);
  });

  it('get defaults to the current period and returns the data', async () => {
    const data = { plan_type: 'free', period: 'May 2025', total_cost: 1.5 };
    mocks.getUsage.mockResolvedValue({ data });

    const result = await usage.get();

    expect(mocks.getUsage).toHaveBeenCalledWith({ client: generated, query: {}, throwOnError: true });
    expect(result).toBe(data);
  });

  it('get forwards the period as a query parameter', async () => {
    mocks.getUsage.mockResolvedValue({ data: {} });

    await usage.get({ period: 'May 2025' });

    expect(mocks.getUsage).toHaveBeenCalledWith({ client: generated, query: { period: 'May 2025' }, throwOnError: true });
  });

  it('logs forwards filters and pagination and returns the page', async () => {
    const data = { items: [], page: 2, page_size: 5, has_next: false, has_previous: true };
    mocks.getUsageLogs.mockResolvedValue({ data });

    const result = await usage.logs({ endpoint: 'sessions.start', page: 2, page_size: 5 });

    expect(mocks.getUsageLogs).toHaveBeenCalledWith({
      client: generated,
      query: { endpoint: 'sessions.start', page: 2, page_size: 5 },
      throwOnError: true,
    });
    expect(result).toBe(data);
  });

  it('propagates rejections from the generated operations', async () => {
    const failure = new Error('boom');
    mocks.getUsage.mockRejectedValue(failure);
    mocks.getUsageLogs.mockRejectedValue(failure);

    await expect(usage.get()).rejects.toBe(failure);
    await expect(usage.logs()).rejects.toBe(failure);
  });
});
