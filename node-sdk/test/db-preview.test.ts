/**
 * `NOTTE_DB_PREVIEW_BRANCH` selects a database branch. The cdp url is what
 * `session.page()` connects to: a preview-branch session is unknown to the
 * default database, so a handshake without the selector is rejected.
 * Mirrors the `cdp_url` cases of `tests/sdk/test_db_preview_routing.py`.
 */
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { NotteClient } from '@/client';
import { Session } from '@/session';
import { sessionDebugInfo, sessionStart } from '@/lib/client/sdk.gen';
import { sessionResponse } from './helpers/session-mocks';

vi.mock('@/lib/client/sdk.gen', () => ({
  sessionStart: vi.fn(),
  sessionStop: vi.fn(),
  sessionDebugInfo: vi.fn(),
}));

vi.mock('@/version-check', async importOriginal => ({
  ...(await importOriginal<typeof import('@/version-check')>()),
  startVersionCheck: vi.fn(),
}));

const BRANCH = 'feature/my-branch';
const ENV_VAR = 'NOTTE_DB_PREVIEW_BRANCH';
const NOTTE_CDP = 'wss://api.notte.cc/sessions/s/debug?token=t';
const WITH_BRANCH = 'wss://api.notte.cc/sessions/s/debug?token=t&db_preview=feature%2Fmy-branch';

/** A started session with the three cdp url sources under our control. */
async function startedSession(options: { requestCdp?: string; responseCdp?: string; debugCdp?: string } = {}): Promise<Session> {
  vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse({ cdp_url: options.responseCdp ?? null }) } as never);
  vi.mocked(sessionDebugInfo).mockResolvedValue({
    data: { debug_url: '', ws: { cdp: options.debugCdp ?? '', recording: '', logs: '' }, tabs: [] },
  } as never);
  const client = new NotteClient({ apiKey: 'test-api-key', baseUrl: 'https://api.notte.cc' }); // pragma: allowlist secret
  const session = new Session(client, { cdp_url: options.requestCdp ?? null });
  await session.start();
  return session;
}

describe('cdpUrl and db preview routing', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.unstubAllEnvs();
    vi.stubEnv(ENV_VAR, '');
    vi.stubEnv('NOTTE_API_URL', '');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('carries the branch on the cdp url from debug info', async () => {
    vi.stubEnv(ENV_VAR, BRANCH);
    const session = await startedSession({ debugCdp: NOTTE_CDP });
    expect(await session.cdpUrl()).toBe(WITH_BRANCH);
    expect(sessionDebugInfo).toHaveBeenCalledTimes(1);
  });

  it('carries the branch on the cdp url from the start response', async () => {
    vi.stubEnv(ENV_VAR, BRANCH);
    const session = await startedSession({ responseCdp: NOTTE_CDP, debugCdp: 'wss://api.notte.cc/unused' });
    expect(await session.cdpUrl()).toBe(WITH_BRANCH);
    expect(sessionDebugInfo).not.toHaveBeenCalled();
  });

  it('leaves a caller-supplied cdp url alone', async () => {
    // that url belongs to another browser provider, not to our API
    vi.stubEnv(ENV_VAR, BRANCH);
    const external = 'wss://connect.browserbase.com/?apiKey=k';
    const session = await startedSession({ requestCdp: external, responseCdp: NOTTE_CDP, debugCdp: NOTTE_CDP });
    expect(await session.cdpUrl()).toBe(external);
    expect(sessionDebugInfo).not.toHaveBeenCalled();
  });

  it('is unchanged without a branch', async () => {
    expect(await (await startedSession({ debugCdp: NOTTE_CDP })).cdpUrl()).toBe(NOTTE_CDP);
    expect(await (await startedSession({ responseCdp: NOTTE_CDP })).cdpUrl()).toBe(NOTTE_CDP);
  });

  it('prefers the explicit client configuration over the environment', async () => {
    vi.stubEnv(ENV_VAR, 'env-branch');
    vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse({ cdp_url: 'wss://api.notte.cc/ws' }) } as never);
    const client = new NotteClient({ apiKey: 'test-api-key', dbPreview: 'main' }); // pragma: allowlist secret
    const session = new Session(client);
    await session.start();
    expect(await session.cdpUrl()).toBe('wss://api.notte.cc/ws?db_preview=main');
  });

  it('throws before the session is started', async () => {
    const client = new NotteClient({ apiKey: 'test-api-key' }); // pragma: allowlist secret
    await expect(new Session(client).cdpUrl()).rejects.toThrow('Session not started');
  });
});
