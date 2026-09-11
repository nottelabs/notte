import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { randomUUID } from 'node:crypto';
import { NotteClient } from '@/client';
import { NotteSecrets, type SecretMetadata } from '@/secrets';
import { config } from 'dotenv';

config();

const NAMESPACE = 'function_env' as const;

describe('Secrets Integration Tests', () => {
  let secrets: NotteSecrets;
  // Uniquely named so concurrent runs never collide, and never listed by name only.
  const name = `NODE_SDK_TEST_${randomUUID().replace(/-/g, '').slice(0, 12).toUpperCase()}`;
  const value = `value-${randomUUID()}`;
  let stored: SecretMetadata | undefined;

  beforeAll(() => {
    const apiKey = process.env.NOTTE_API_KEY;
    if (!apiKey) {
      throw new Error('NOTTE_API_KEY environment variable is required for integration tests');
    }
    const client = new NotteClient({ apiKey, baseUrl: process.env.NOTTE_API_URL || 'https://api.notte.cc' });
    secrets = new NotteSecrets(client);
  });

  afterAll(async () => {
    if (!stored) return;
    try {
      await secrets.delete(stored.id);
    } catch (error) {
      // Already deleted by the last test; anything else is worth surfacing.
      console.warn(`Failed to clean up secret ${stored.id}: ${String(error)}`);
    }
  });

  it('store → get → list → delete an owned secret', async () => {
    stored = await secrets.store({ namespace: NAMESPACE, name, value });
    expect(typeof stored.id).toBe('string');
    expect(stored.name).toBe(name);
    expect(stored.namespace).toBe(NAMESPACE);
    expect(typeof stored.key_hint).toBe('string');
    expect(typeof stored.created_at).toBe('string');

    const fetched = await secrets.get(name, NAMESPACE);
    expect(fetched.value).toBe(value);

    const listed = await secrets.list({ namespace: NAMESPACE });
    const mine = listed.find(item => item.id === stored!.id);
    expect(mine).toBeDefined();
    expect(mine!.name).toBe(name);
    expect(listed.every(item => item.namespace === NAMESPACE)).toBe(true);

    await secrets.delete(stored.id);
    const afterDelete = await secrets.list({ namespace: NAMESPACE });
    expect(afterDelete.some(item => item.id === stored!.id)).toBe(false);
    stored = undefined;
  });
});
