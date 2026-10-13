import { expect, it } from 'vitest';
import { NotteClient } from '@/client';

it('creates and cleans up owned API resources through generated namespaces', async () => {
  if (!process.env.NOTTE_API_KEY || !process.env.NOTTE_API_URL) {
    throw new Error('Set NOTTE_API_KEY and an explicit NOTTE_API_URL for live resource tests');
  }
  const client = new NotteClient();
  const vault = await client.vaults.create({ name: 'generated-resource-test' });
  try {
    expect(vault.vault_id).toBeTruthy();
    const session = await client.sessions.start({ proxies: false });
    try {
      expect(session.session_id).toBeTruthy();
      expect((await client.sessions.status(session.session_id)).status).toBe('active');
    } finally {
      const stopped = await client.sessions.stop(session.session_id);
      expect(stopped.status).toBe('closed');
    }
  } finally {
    await client.vaults.delete(vault.vault_id);
  }
}, 120_000);
