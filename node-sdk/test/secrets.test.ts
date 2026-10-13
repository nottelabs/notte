import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { NotteClient } from '@/client';

const mocks = vi.hoisted(() => ({
  listSecrets: vi.fn(),
  storeSecret: vi.fn(),
  getSecret: vi.fn(),
  deleteSecret: vi.fn(),
}));

vi.mock('@/lib/client/sdk.gen', () => mocks);

import { NotteSecrets } from '@/secrets';

const metadata = {
  id: 'sec-1',
  namespace: 'function_env' as const,
  name: 'MY_TOKEN',
  key_hint: 'xy***',
  created_at: '2025-01-01T00:00:00Z',
  last_used_at: null,
};

describe('NotteSecrets', () => {
  const generated = { id: 'test-client' };
  const client = { getClient: () => generated } as unknown as NotteClient;
  let secrets: NotteSecrets;

  beforeEach(() => {
    Object.values(mocks).forEach(mock => mock.mockReset());
    secrets = new NotteSecrets(client);
  });

  describe('list', () => {
    it('lists every namespace by default and unwraps items', async () => {
      mocks.listSecrets.mockResolvedValue({ data: { items: [metadata] } });

      const result = await secrets.list();

      expect(mocks.listSecrets).toHaveBeenCalledWith({ client: generated, query: {}, throwOnError: true });
      expect(result).toEqual([metadata]);
    });

    it('passes the namespace filter as a query parameter', async () => {
      mocks.listSecrets.mockResolvedValue({ data: { items: [] } });

      await secrets.list({ namespace: 'llm_provider' });

      expect(mocks.listSecrets).toHaveBeenCalledWith({
        client: generated,
        query: { namespace: 'llm_provider' },
        throwOnError: true,
      });
    });

    it('returns an empty array when the API sends no body', async () => {
      mocks.listSecrets.mockResolvedValue({ data: undefined });

      await expect(secrets.list()).resolves.toEqual([]);
    });
  });

  it('store posts the body and returns the metadata', async () => {
    mocks.storeSecret.mockResolvedValue({ data: metadata });
    const body = { namespace: 'function_env' as const, name: 'MY_TOKEN', value: 'xyz' };

    const result = await secrets.store(body);

    expect(mocks.storeSecret).toHaveBeenCalledWith({ client: generated, body, throwOnError: true });
    expect(result).toBe(metadata);
  });

  it('get addresses the secret by name path and namespace query', async () => {
    mocks.getSecret.mockResolvedValue({ data: { value: 'xyz' } });

    const result = await secrets.get('MY_TOKEN', 'function_env');

    expect(mocks.getSecret).toHaveBeenCalledWith({
      client: generated,
      path: { name: 'MY_TOKEN' },
      query: { namespace: 'function_env' },
      throwOnError: true,
    });
    expect(result).toEqual({ value: 'xyz' });
  });

  it('delete addresses the secret by id and resolves to void', async () => {
    mocks.deleteSecret.mockResolvedValue({ data: undefined });

    await expect(secrets.delete('sec-1')).resolves.toBeUndefined();

    expect(mocks.deleteSecret).toHaveBeenCalledWith({
      client: generated,
      path: { secret_id: 'sec-1' },
      throwOnError: true,
    });
  });

  it('propagates rejections from every generated operation', async () => {
    const failure = new Error('boom');
    mocks.listSecrets.mockRejectedValue(failure);
    mocks.storeSecret.mockRejectedValue(failure);
    mocks.getSecret.mockRejectedValue(failure);
    mocks.deleteSecret.mockRejectedValue(failure);

    await expect(secrets.list()).rejects.toBe(failure);
    await expect(secrets.store({ namespace: 'function_env', name: 'a', value: 'b' })).rejects.toBe(failure);
    await expect(secrets.get('a', 'function_env')).rejects.toBe(failure);
    await expect(secrets.delete('sec-1')).rejects.toBe(failure);
  });
});
