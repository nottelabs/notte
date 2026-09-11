import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NotteClient } from '@/client';

const mocks = vi.hoisted(() => ({
  vaultCreate: vi.fn(),
  vaultCredentialsAdd: vi.fn(),
  vaultCredentialsGet: vi.fn(),
  vaultCredentialsDelete: vi.fn(),
  vaultDelete: vi.fn(),
  vaultCredentialsList: vi.fn(),
  vaultCreditCardSet: vi.fn(),
  vaultCreditCardGet: vi.fn(),
  vaultCreditCardDelete: vi.fn(),
}));

vi.mock('@/lib/client/sdk.gen', () => mocks);

import { NotteVault } from '@/vaults';

describe('NotteVault initialization', () => {
  const client = {
    getClient: () => ({ id: 'test-client' }),
  } as unknown as NotteClient;

  beforeEach(() => {
    Object.values(mocks).forEach(mock => mock.mockReset());
    mocks.vaultCreate.mockResolvedValue({
      data: { vault_id: 'owned-vault-id', name: 'test', created_at: new Date().toISOString() },
    });
    mocks.vaultCredentialsList.mockResolvedValue({ data: { credentials: [] } });
  });

  it('does not create a remote vault when using a local-only password helper', () => {
    const vault = new NotteVault(client);

    expect(vault.generatePassword()).toBeTypeOf('string');
    expect(mocks.vaultCreate).not.toHaveBeenCalled();
  });

  it('creates the remote vault once when an API operation needs it', async () => {
    const vault = new NotteVault(client);

    await vault.listCredentials();
    await vault.listCredentials();

    expect(mocks.vaultCreate).toHaveBeenCalledTimes(1);
    expect(vault.vaultId).toBe('owned-vault-id');
  });
});
