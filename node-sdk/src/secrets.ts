import type { NotteClient } from '@/client';
import type {
  ListSecretsData,
  SecretListResponse,
  SecretMetadata,
  SecretNamespace,
  SecretStoreRequest,
  SecretValueResponse,
} from '@/lib/client/types.gen';
import { deleteSecret, getSecret, listSecrets, storeSecret } from '@/lib/client/sdk.gen';

/** Options of `client.secrets.list()`: optionally filter by namespace. */
export type SecretListOptions = NonNullable<ListSecretsData['query']>;
/** Body of `client.secrets.store()`. */
export type SecretStoreOptions = SecretStoreRequest;

export type { SecretListResponse, SecretMetadata, SecretNamespace, SecretValueResponse };

/**
 * Workspace secrets store, the counterpart of the `/secrets` endpoints.
 * Secrets are scoped by namespace: `llm_provider` keys are used by agents and
 * scraping, `function_env` values are injected into function runs.
 *
 * ```ts
 * await client.secrets.store({ namespace: 'function_env', name: 'MY_TOKEN', value: 'xyz' });
 * const secrets = await client.secrets.list({ namespace: 'function_env' });
 * ```
 */
export class NotteSecrets {
  private readonly client: NotteClient;

  constructor(client: NotteClient) {
    this.client = client;
  }

  /**
   * List secret metadata (never the values), optionally filtered by namespace.
   *
   * ```ts
   * const secrets = await client.secrets.list({ namespace: 'llm_provider' });
   * secrets.forEach(s => console.log(s.name, s.key_hint));
   * ```
   */
  async list(options: SecretListOptions = {}): Promise<SecretMetadata[]> {
    const response = await listSecrets({ client: this.client.getClient(), query: options, throwOnError: true });
    return response.data?.items ?? [];
  }

  /**
   * Store (or overwrite) a secret and return its metadata.
   *
   * ```ts
   * const meta = await client.secrets.store({ namespace: 'function_env', name: 'API_TOKEN', value: 'xyz' });
   * console.log(meta.id, meta.key_hint);
   * ```
   */
  async store(body: SecretStoreOptions): Promise<SecretMetadata> {
    const response = await storeSecret({ client: this.client.getClient(), body, throwOnError: true });
    return response.data;
  }

  /**
   * Read the value of a secret by name within a namespace.
   *
   * ```ts
   * const { value } = await client.secrets.get('API_TOKEN', 'function_env');
   * ```
   */
  async get(name: string, namespace: SecretNamespace): Promise<SecretValueResponse> {
    const response = await getSecret({
      client: this.client.getClient(),
      path: { name },
      query: { namespace },
      throwOnError: true,
    });
    return response.data;
  }

  /**
   * Delete a secret by id (the `id` field of `SecretMetadata`).
   *
   * ```ts
   * const meta = await client.secrets.store({ namespace: 'function_env', name: 'TMP', value: 'x' });
   * await client.secrets.delete(meta.id);
   * ```
   */
  async delete(secretId: string): Promise<void> {
    await deleteSecret({ client: this.client.getClient(), path: { secret_id: secretId }, throwOnError: true });
  }
}
