import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { NotteClient } from '@/client';

const mocks = vi.hoisted(() => ({
  searchWeb: vi.fn(),
}));

vi.mock('@/lib/client/sdk.gen', () => mocks);

import { NotteSearch } from '@/search';

describe('NotteSearch', () => {
  const generated = { id: 'test-client' };
  const client = { getClient: () => generated } as unknown as NotteClient;
  let search: NotteSearch;

  beforeEach(() => {
    mocks.searchWeb.mockReset();
    search = new NotteSearch(client);
  });

  it('posts the query as `q` and returns the data', async () => {
    const data = { results: [{ url: 'https://notte.cc', name: 'Notte', content: 'Browser automation' }] };
    mocks.searchWeb.mockResolvedValue({ data });

    const result = await search.search('notte browser automation');

    expect(mocks.searchWeb).toHaveBeenCalledTimes(1);
    expect(mocks.searchWeb).toHaveBeenCalledWith({
      client: generated,
      body: { q: 'notte browser automation' },
      throwOnError: true,
    });
    expect(result).toBe(data);
  });

  it('forwards options and keeps the positional query authoritative', async () => {
    mocks.searchWeb.mockResolvedValue({ data: { answer: 'yes', sources: [] } });

    const result = await search.search('what is notte?', {
      outputType: 'sourcedAnswer',
      depth: 'deep',
      maxResults: 3,
    });

    expect(mocks.searchWeb).toHaveBeenCalledWith({
      client: generated,
      body: { q: 'what is notte?', outputType: 'sourcedAnswer', depth: 'deep', maxResults: 3 },
      throwOnError: true,
    });
    expect(result.answer).toBe('yes');
  });

  it('propagates rejections from the generated operation', async () => {
    const failure = new Error('boom');
    mocks.searchWeb.mockRejectedValue(failure);

    await expect(search.search('anything')).rejects.toBe(failure);
  });
});
