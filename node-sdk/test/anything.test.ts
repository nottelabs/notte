import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { NotteClient } from '@/client';

const mocks = vi.hoisted(() => ({
  anythingStart: vi.fn(),
}));

vi.mock('@/lib/client/sdk.gen', () => mocks);

import { NotteAnything } from '@/anything';

describe('NotteAnything', () => {
  const generated = { id: 'test-client' };
  const client = { getClient: () => generated } as unknown as NotteClient;
  let anything: NotteAnything;

  beforeEach(() => {
    mocks.anythingStart.mockReset();
    anything = new NotteAnything(client);
  });

  it('posts the task body and returns the data', async () => {
    const data = { function_id: 'fn-123', status: 'building' };
    mocks.anythingStart.mockResolvedValue({ data });

    const result = await anything.start({ task: 'fetch the top 3 hacker news posts' });

    expect(mocks.anythingStart).toHaveBeenCalledTimes(1);
    expect(mocks.anythingStart).toHaveBeenCalledWith({
      client: generated,
      body: { task: 'fetch the top 3 hacker news posts' },
      throwOnError: true,
    });
    expect(result).toBe(data);
  });

  it('returns an empty object when the API sends no body', async () => {
    mocks.anythingStart.mockResolvedValue({ data: undefined });

    await expect(anything.start({ task: 'noop' })).resolves.toEqual({});
  });

  it('propagates rejections from the generated operation', async () => {
    const failure = new Error('boom');
    mocks.anythingStart.mockRejectedValue(failure);

    await expect(anything.start({ task: 'x' })).rejects.toBe(failure);
  });
});
