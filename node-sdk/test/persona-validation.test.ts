import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NotteClient } from '@/client';
import { NotteAPIError } from '@/errors';
import type { PersonaConstructor } from '@/personas';

describe('persona server validation parity', () => {
  const requests: Request[] = [];
  beforeEach(() => {
    requests.length = 0;
    vi.stubEnv('NOTTE_SDK_DISABLE_VERSION_CHECK', '1');
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
      requests.push(request.clone());
      return Response.json({ detail: 'invalid create_vault' }, { status: 422 });
    }));
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks(); });

  it('sends invalid create input unchanged and surfaces a typed API 422', async () => {
    const client = new NotteClient({ apiKey: 'synthetic-key', baseUrl: 'https://api.example.test' }); // pragma: allowlist secret
    const input = { create_vault: 'invalid' };
    const persona = client.Persona(input as unknown as PersonaConstructor);
    const pending = persona.start();
    await expect(pending).rejects.toBeInstanceOf(NotteAPIError);
    await expect(pending).rejects.toMatchObject({ statusCode: 422 });
    expect(requests).toHaveLength(1);
    expect(requests[0]!.method).toBe('POST');
    expect(new URL(requests[0]!.url).pathname).toBe('/personas/create');
    expect(await requests[0]!.json()).toEqual(input);
  });
});
