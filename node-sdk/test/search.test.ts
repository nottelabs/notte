import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NotteClient } from '@/client';

const mocks = vi.hoisted(() => ({
  searchWeb: vi.fn(),
}));

vi.mock('@/lib/client/sdk.gen', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/lib/client/sdk.gen')>(),
  ...mocks,
}));

describe('NotteClient.search', () => {
  let client: NotteClient;

  beforeEach(() => {
    mocks.searchWeb.mockReset();
    client = new NotteClient({ apiKey: 'test-key' }); // pragma: allowlist secret (test fixture)
  });

  it('posts the query as `q` and returns the data', async () => {
    const data = { results: [{ url: 'https://notte.cc', name: 'Notte', content: 'Browser automation' }] };
    mocks.searchWeb.mockResolvedValue({ data });

    const result = await client.search('notte browser automation');

    expect(mocks.searchWeb).toHaveBeenCalledTimes(1);
    expect(mocks.searchWeb).toHaveBeenCalledWith({
      client: client.getClient(),
      body: { q: 'notte browser automation' },
      throwOnError: true,
    });
    expect(result).toBe(data);
  });

  it('forwards search options', async () => {
    mocks.searchWeb.mockResolvedValue({ data: { answer: 'yes', sources: [] } });

    const result = await client.search('what is notte?', {
      outputType: 'sourcedAnswer',
      depth: 'deep',
      maxResults: 3,
    });

    expect(mocks.searchWeb).toHaveBeenCalledWith({
      client: client.getClient(),
      body: { q: 'what is notte?', outputType: 'sourcedAnswer', depth: 'deep', maxResults: 3 },
      throwOnError: true,
    });
    expect(result.answer).toBe('yes');
  });

  it('propagates rejections from the generated operation', async () => {
    const failure = new Error('boom');
    mocks.searchWeb.mockRejectedValue(failure);

    await expect(client.search('anything')).rejects.toBe(failure);
  });
});
