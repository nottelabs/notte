import { InvalidRequestError } from '@/errors';
import type { NotteVault } from '@/vaults';
import { NotteClient } from '@/client';
import { vaultDelete } from '@/lib/client/sdk.gen';

const DELETE_BATCH_SIZE = 5;

export async function cleanupVaults(client: NotteClient, vaultIds: Iterable<string>): Promise<void> {
  const ownedVaultIds = [...new Set(vaultIds)].filter(Boolean);

  for (let offset = 0; offset < ownedVaultIds.length; offset += DELETE_BATCH_SIZE) {
    const batch = ownedVaultIds.slice(offset, offset + DELETE_BATCH_SIZE);
    const results = await Promise.allSettled(
      batch.map(async vaultId => {
        // The client is configured with throwOnError, so a failed delete rejects
        // with a NotteAPIError instead of resolving with `{ error }`.
        await vaultDelete({
          client: client.getClient(),
          path: { vault_id: vaultId },
          throwOnError: true,
        });
      }),
    );

    results.forEach((result, index) => {
      if (result.status === 'rejected') {
        console.warn(`Failed to delete owned vault ${batch[index]} during cleanup: ${result.reason}`);
      }
    });
  }
}


/** Initialize a test-owned vault and register its ID for the caller's cleanup. */
export async function initializeOwnedVault(
  vault: Pick<NotteVault, 'listCredentials' | 'vaultId'>, vaultIds: string[],
): Promise<void> {
  try {
    await vault.listCredentials();
  } finally {
    try {
      vaultIds.push(vault.vaultId);
    } catch (error) {
      // A failed create has no ID; preserve that original error.
      if (!(error instanceof InvalidRequestError)) throw error;
    }
  }
}
