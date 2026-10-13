import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NotteClient } from '@/client';

const { vaultDeleteMock } = vi.hoisted(() => ({
  vaultDeleteMock: vi.fn(),
}));

vi.mock('@/lib/client/sdk.gen', () => ({
  vaultDelete: vaultDeleteMock,
}));

import { cleanupVaults } from './helpers/cleanup-vaults';

describe('cleanupVaults', () => {
  const client = {
    getClient: () => ({ id: 'test-client' }),
  } as unknown as NotteClient;

  beforeEach(() => {
    vaultDeleteMock.mockReset();
    vaultDeleteMock.mockResolvedValue({ data: { status: 'success' } });
  });

  it('deletes only the exact vault IDs supplied by its own test', async () => {
    await cleanupVaults(client, ['owned-vault-1', 'owned-vault-2', 'owned-vault-1']);

    expect(vaultDeleteMock).toHaveBeenCalledTimes(2);
    expect(vaultDeleteMock.mock.calls.map(([request]) => request.path.vault_id)).toEqual([
      'owned-vault-1',
      'owned-vault-2',
    ]);
  });

  it('does not discover or delete any vault when no owned IDs are supplied', async () => {
    await cleanupVaults(client, []);

    expect(vaultDeleteMock).not.toHaveBeenCalled();
  });

  it('keeps deleting the remaining vaults when one delete rejects', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    vaultDeleteMock.mockImplementation(async ({ path }: { path: { vault_id: string } }) => {
      if (path.vault_id === 'gone') {
        throw new Error('404');
      }
      return { data: { status: 'success' } };
    });

    await expect(cleanupVaults(client, ['gone', 'owned-vault-2'])).resolves.toBeUndefined();

    expect(vaultDeleteMock).toHaveBeenCalledTimes(2);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('Failed to delete owned vault gone'));
    warn.mockRestore();
  });
});
