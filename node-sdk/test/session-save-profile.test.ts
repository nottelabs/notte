import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Session } from '@/session';
import { sessionProfileSave, sessionStart } from '@/lib/client/sdk.gen';
import type { ProfileResponse } from '@/lib/client/types.gen';
import { mockNotteClient, sessionResponse } from './helpers/session-mocks';

vi.mock('@/lib/client/sdk.gen', () => ({
  sessionStart: vi.fn(),
  sessionStop: vi.fn(),
  sessionProfileSave: vi.fn(),
}));

vi.mock('@/utils', () => ({
  formatError: (error: unknown) => String(error),
  openBrowser: vi.fn(),
}));

const profile: ProfileResponse = {
  profile_id: 'notte-profile-0123456789abcdef',
  name: 'github',
  created_at: '2026-10-13T00:00:00Z',
  updated_at: '2026-10-13T00:00:00Z',
  persisted_domains: ['github.com'],
};

describe('session.saveProfile', () => {
  let session: Session;

  beforeEach(async () => {
    vi.resetAllMocks();
    vi.spyOn(console, 'info').mockImplementation(() => {});
    vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse() } as never);
    vi.mocked(sessionProfileSave).mockResolvedValue({ data: profile } as never);
    session = new Session(mockNotteClient());
    await session.start();
  });

  it.each([
    [{ profile_id: 'notte-profile-0123456789abcdef' }, { profile_id: 'notte-profile-0123456789abcdef' }],
    [{ name: 'github' }, { name: 'github' }],
    [{}, {}],
  ])('sends %o as the save target', async (options, body) => {
    const saved = await session.saveProfile(options);

    expect(sessionProfileSave).toHaveBeenCalledTimes(1);
    const call = vi.mocked(sessionProfileSave).mock.calls[0]![0];
    expect(call.path).toEqual({ session_id: sessionResponse().session_id });
    expect(call.body).toEqual(body);
    expect(call.throwOnError).toBe(true);
    expect(saved.persisted_domains).toEqual(['github.com']);
  });

  it.each([
    [{ profile_id: 'notte-profile-0123456789abcdef', name: 'github' }, /mutually exclusive/],
    [{ profile_id: ' ' }, /profile_id must not be empty/],
    [{ name: '' }, /name must not be empty/],
  ])('rejects %o without calling the API', async (options, message) => {
    await expect(session.saveProfile(options)).rejects.toThrow(message);
    expect(sessionProfileSave).not.toHaveBeenCalled();
  });

  it('requires a started session', async () => {
    const fresh = new Session(mockNotteClient());
    await expect(fresh.saveProfile({ name: 'github' })).rejects.toThrow();
    expect(sessionProfileSave).not.toHaveBeenCalled();
  });
});
