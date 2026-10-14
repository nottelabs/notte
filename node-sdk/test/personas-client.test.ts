import { afterEach, expect, it, vi } from 'vitest';
import { NotteClient } from '@/client';

afterEach(() => vi.unstubAllGlobals());

const persona = (extra: Record<string, unknown> = {}) => ({
  persona_id: 'persona_123',
  status: 'active',
  first_name: 'Amy',
  last_name: 'Ferguson',
  email: 'amy.ferguson@example.com',
  internal_email: 'persona_123@example.com',
  vault_id: null,
  phone_number: null,
  ...extra
});

it('defaults email_provider to notte on persona collection responses', async () => {
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    const { pathname } = new URL(request.url);
    if (pathname === '/personas') {
      return Response.json({ items: [persona(), persona({ email_provider: 'agentmail' })] });
    }
    return Response.json(persona());
  }));
  const client = new NotteClient({ baseUrl: 'https://api.example', apiKey: 'test-key' }); // pragma: allowlist secret

  expect((await client.personas.get('persona_123'))?.email_provider).toBe('notte');
  expect((await client.personas.create({}))?.email_provider).toBe('notte');
  expect((await client.personas.list()).map(p => p.email_provider)).toEqual(['notte', 'agentmail']);
});
