import { NotteClient } from '@/client';
import { vaultDelete } from '@/lib/client/sdk.gen';

const DELETE_BATCH_SIZE = 5;

export async function cleanupVaults(client: NotteClient, vaultIds: Iterable<string>): Promise<void> {
  const ownedVaultIds = [...new Set(vaultIds)].filter(Boolean);

  for (let offset = 0; offset < ownedVaultIds.length; offset += DELETE_BATCH_SIZE) {
    const batch = ownedVaultIds.slice(offset, offset + DELETE_BATCH_SIZE);
    const results = await Promise.allSettled(
      batch.map(async vaultId => {
        const response = await vaultDelete({
          client: client.getClient(),
          path: { vault_id: vaultId },
        });
        if (response.error) {
          throw new Error(JSON.stringify(response.error));
        }
      }),
    );

    results.forEach((result, index) => {
      if (result.status === 'rejected') {
        console.warn(`Failed to delete owned vault ${batch[index]} during cleanup: ${result.reason}`);
      }
    });
  }
}
