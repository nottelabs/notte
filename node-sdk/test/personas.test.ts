import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { NotteClient } from '@/client';

const mocks = vi.hoisted(() => ({
  personaGet: vi.fn(),
  personaCreate: vi.fn(),
  personaDelete: vi.fn(),
  personaEmailsList: vi.fn(),
  personaSmsList: vi.fn(),
  listPersonas: vi.fn()
}));

vi.mock('@/lib/client/sdk.gen', () => mocks);

import { NottePersona } from '@/personas';

describe('NottePersona email addresses', () => {
  const client = {
    getClient: () => ({ id: 'test-client' })
  } as unknown as NotteClient;

  beforeEach(() => {
    Object.values(mocks).forEach(mock => mock.mockReset());
    mocks.personaGet.mockResolvedValue({
      data: {
        persona_id: '8d5a3550-733f-4d32-8f41-62451f770537',
        status: 'active',
        first_name: 'Amy',
        last_name: 'Ferguson',
        email: 'amy.ferguson@mail-sand.com',
        internal_email: '8d5a3550-733f-4d32-8f41-62451f770537@mail-sand.com',
        vault_id: null,
        phone_number: null
      }
    });
  });

  it('exposes the public and internal addresses directly', async () => {
    const persona = new NottePersona(client, {
      persona_id: '8d5a3550-733f-4d32-8f41-62451f770537'
    });
    await persona.get();

    expect(persona.email).toBe('amy.ferguson@mail-sand.com');
    expect(persona.internalEmail).toBe(
      '8d5a3550-733f-4d32-8f41-62451f770537@mail-sand.com'
    );
    expect(persona.info.internal_email).toBe(persona.internalEmail);
  });

  it.each([false, true])('never deletes a borrowed persona, callback throws=%s', async throws => {
    const persona = new NottePersona(client, { persona_id: 'existing' });
    const result = persona.use(async p => {
      expect(p.info.persona_id).toBeDefined();
      if (throws) throw new Error('callback failed');
      return 'ok';
    });
    if (throws) await expect(result).rejects.toThrow('callback failed');
    else await expect(result).resolves.toBe('ok');
    expect(mocks.personaDelete).not.toHaveBeenCalled();
  });

  it('shares creation across constructor, start, create and get', async () => {
    let finish!: (value: unknown) => void;
    mocks.personaCreate.mockReturnValue(new Promise(resolve => { finish = resolve; }));
    const persona = new NottePersona(client);
    const pending = Promise.all([persona.start(), persona.start(), persona.create(), persona.get()]);
    expect(mocks.personaCreate).toHaveBeenCalledTimes(1);
    finish({ data: { persona_id: 'owned' } });
    await pending;
    mocks.personaDelete.mockResolvedValue({ data: {} });
    await persona.use(async p => expect(p.personaId).toBe('owned'));
    expect(mocks.personaDelete).toHaveBeenCalledTimes(1);
  });
});
