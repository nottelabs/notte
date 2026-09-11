import { afterEach, beforeEach, describe, it, expect, expectTypeOf, vi } from 'vitest';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { CLUSTER_OVERLOAD_RETRY_DELAY_MS, Session, type SessionOptions } from '@/session';
import type { RemoteFileStorage } from '@/files';
import { NotteAPIError, NotteTimeoutError, sleep } from '@/errors';
import {
  getSessionScript,
  pageObserve,
  sessionCookiesGet,
  sessionCookiesSet,
  sessionDebugInfo,
  sessionReplay,
  sessionStart,
  sessionStatus,
  sessionStop,
} from '@/lib/client/sdk.gen';
import type { Cookie, ReplayResponse, SessionDebugResponse } from '@/index';
import { openBrowser } from '@/utils';
import { mockNotteClient, sessionResponse } from './helpers/session-mocks';

vi.mock('@/lib/client/sdk.gen', () => ({
  sessionStart: vi.fn(),
  sessionStop: vi.fn(),
  sessionStatus: vi.fn(),
  sessionCookiesSet: vi.fn(),
  sessionCookiesGet: vi.fn(),
  sessionDebugInfo: vi.fn(),
  getSessionScript: vi.fn(),
  pageExecute: vi.fn(),
  pageObserve: vi.fn(),
  sessionReplay: vi.fn(),
  pageScrape: vi.fn(),
}));

vi.mock('@/utils', () => ({
  formatError: (error: unknown) => String(error),
  openBrowser: vi.fn(),
}));

vi.mock('@/errors', async importOriginal => ({
  ...(await importOriginal<typeof import('@/errors')>()),
  sleep: vi.fn(async () => {}),
}));

const apiError = (status: number, body: Record<string, unknown> = {}) => new NotteAPIError('/sessions/start', status, body);

describe('Session Unit Tests', () => {
  let mockClient: ReturnType<typeof mockNotteClient>;
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.resetAllMocks();
    mockClient = mockNotteClient();
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'info').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse() } as never);
    vi.mocked(sessionStop).mockResolvedValue({ data: sessionResponse({ status: 'closed' }) } as never);
  });

  describe('constructor', () => {
    it('should create session with default options', () => {
      const session = new Session(mockClient);
      expect(session).toBeDefined();
      expect(session.getId()).toBeNull();
      expect(session.isSessionActive()).toBe(false);
      expect(session.storage).toBeUndefined();
    });

    it('should accept open_viewer as a local option', () => {
      const session = new Session(mockClient, { headless: true, open_viewer: true });
      expect(session.getId()).toBeNull();
    });

    it('should retain the deprecated headless option as a local compatibility type', () => {
      const headless: boolean = true;
      const options: SessionOptions = { headless };
      expectTypeOf<SessionOptions['headless']>().toEqualTypeOf<boolean | undefined>();
      expect(options.headless).toBe(true);
    });
  });

  describe('start', () => {
    it('should discard deprecated headless true before calling the API', async () => {
      const session = new Session(mockClient, { headless: true });
      await session.start();

      expect(sessionStart).toHaveBeenCalledWith(expect.objectContaining({ body: {} }));
      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('`headless: true` is deprecated'));
    });

    it('should reject deprecated headless false when starting with a migration error', async () => {
      const session = new Session(mockClient, { headless: false });
      await expect(session.start()).rejects.toThrow('Remote `headless: false` is no longer supported.');
      expect(sessionStart).not.toHaveBeenCalled();
    });

    it('does not send local options to the API', async () => {
      const session = new Session(mockClient, {
        open_viewer: false,
        raiseOnFailure: false,
        perception_type: 'deep',
        proxies: false,
      });
      await session.start();
      expect(sessionStart).toHaveBeenCalledWith(expect.objectContaining({ body: { proxies: false } }));
      expect(session.getId()).toBe('session-123');
      expect(session.isSessionActive()).toBe(true);
    });

    it('rejects when the session is already active', async () => {
      const session = new Session(mockClient);
      await session.start();
      await expect(session.start()).rejects.toThrow('Session is already active');
      expect(sessionStart).toHaveBeenCalledTimes(1);
    });

    it('retries on 5xx errors without sleeping and succeeds', async () => {
      vi.mocked(sessionStart)
        .mockRejectedValueOnce(apiError(503))
        .mockRejectedValueOnce(apiError(500))
        .mockResolvedValueOnce({ data: sessionResponse({ session_id: 'after-retry' }) } as never);
      const session = new Session(mockClient);

      await session.start();

      expect(session.getId()).toBe('after-retry');
      expect(sessionStart).toHaveBeenCalledTimes(3);
      expect(sleep).not.toHaveBeenCalled();
      expect(warnSpy).toHaveBeenCalledWith('Failed to start session: retrying (1/2)');
      expect(warnSpy).toHaveBeenCalledWith('Failed to start session: retrying (2/2)');
    });

    it('waits CLUSTER_OVERLOAD_RETRY_DELAY_MS before retrying on 529', async () => {
      vi.mocked(sessionStart)
        .mockRejectedValueOnce(apiError(529, { message: 'cluster overload' }))
        .mockResolvedValueOnce({ data: sessionResponse() } as never);
      const session = new Session(mockClient);

      await session.start();

      expect(sleep).toHaveBeenCalledTimes(1);
      expect(sleep).toHaveBeenCalledWith(CLUSTER_OVERLOAD_RETRY_DELAY_MS);
      expect(CLUSTER_OVERLOAD_RETRY_DELAY_MS).toBe(30_000);
      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('cluster overload, retrying in 30 seconds (1/2)'));
    });

    it('never retries 4xx errors', async () => {
      const error = apiError(401, { message: 'invalid api key' });
      vi.mocked(sessionStart).mockRejectedValue(error);
      const session = new Session(mockClient);

      await expect(session.start()).rejects.toBe(error);
      expect(sessionStart).toHaveBeenCalledTimes(1);
      expect(session.isSessionActive()).toBe(false);
    });

    it('gives up after three attempts and rethrows the typed error', async () => {
      const error = apiError(502);
      vi.mocked(sessionStart).mockRejectedValue(error);
      const session = new Session(mockClient);

      await expect(session.start()).rejects.toBe(error);
      expect(sessionStart).toHaveBeenCalledTimes(3);
    });

    it('does not retry non-API errors', async () => {
      vi.mocked(sessionStart).mockRejectedValue(new TypeError('fetch failed'));
      await expect(new Session(mockClient).start()).rejects.toThrow('fetch failed');
      expect(sessionStart).toHaveBeenCalledTimes(1);
    });
  });

  describe('stop', () => {
    it('is a no-op when the session was not started', async () => {
      await new Session(mockClient).stop();
      expect(sessionStop).not.toHaveBeenCalled();
    });

    it('sends the close reason and records the closed response', async () => {
      const session = new Session(mockClient);
      await session.start();
      await session.stop('manual');

      expect(sessionStop).toHaveBeenCalledWith(
        expect.objectContaining({ path: { session_id: 'session-123' }, query: { close_reason: 'manual' } }),
      );
      expect(session.getResponse()?.status).toBe('closed');
      expect(session.getId()).toBeNull();
      expect(session.isSessionActive()).toBe(false);
    });

    it('tolerates a session the API reports as already stopped', async () => {
      vi.mocked(sessionStop).mockRejectedValue(apiError(400, { message: 'Session session-123 is already stopped' }));
      const session = new Session(mockClient);
      await session.start();

      await expect(session.stop()).resolves.toBeUndefined();
      expect(warnSpy).toHaveBeenCalledWith('Session session-123 was already stopped');
      expect(session.isSessionActive()).toBe(false);
    });

    it('rejects when the API reports a status other than closed', async () => {
      vi.mocked(sessionStop).mockResolvedValue({ data: sessionResponse({ status: 'active' }) } as never);
      const session = new Session(mockClient);
      await session.start();
      await expect(session.stop()).rejects.toThrow('[Session] session-123 failed to stop');
      // the session is left active so the caller can retry
      expect(session.isSessionActive()).toBe(true);
    });

    it('rethrows other stop errors', async () => {
      const error = apiError(500, { message: 'boom' });
      vi.mocked(sessionStop).mockRejectedValue(error);
      const session = new Session(mockClient);
      await session.start();
      await expect(session.stop()).rejects.toBe(error);
    });
  });

  describe('status', () => {
    it('returns the session status', async () => {
      vi.mocked(sessionStatus).mockResolvedValue({ data: sessionResponse({ status: 'active' }) } as never);
      const session = new Session(mockClient);
      await session.start();
      expect((await session.status()).status).toBe('active');
      expect(sessionStatus).toHaveBeenCalledWith(expect.objectContaining({ path: { session_id: 'session-123' } }));
    });

    it('rejects when not started', async () => {
      await expect(new Session(mockClient).status()).rejects.toThrow('Session not started');
    });
  });

  describe('replay', () => {
    const replays = [
      { mp4_url: 'https://example.com/replay.mp4', expires_at: '2099-01-01T00:00:00Z' },
      { playlist_content: '#EXTM3U\n#EXT-X-ENDLIST', expires_at: '2099-01-01T00:00:00Z' },
    ] satisfies ReplayResponse[];

    it.each(replays)('retrieves the last closed session without marking it active (%j)', async replay => {
      vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse({ session_id: 'session-replay' }) } as never);
      vi.mocked(sessionStop).mockResolvedValue({ data: sessionResponse({ session_id: 'session-replay', status: 'closed' }) } as never);
      vi.mocked(sessionReplay).mockResolvedValue({ data: replay } as never);
      const session = new Session(mockClient);
      await session.start();
      await session.stop();

      expectTypeOf<ReturnType<Session['replay']>>().toEqualTypeOf<Promise<ReplayResponse>>();
      expect(await session.replay()).toEqual(replay);
      expect(sessionReplay).toHaveBeenCalledWith(expect.objectContaining({ path: { session_id: 'session-replay' } }));
      expect(session.getId()).toBeNull();
      expect(session.isSessionActive()).toBe(false);
    });

    it('rejects replay when no session has been created', async () => {
      await expect(new Session(mockClient).replay()).rejects.toThrow('Session not started');
      expect(sessionReplay).not.toHaveBeenCalled();
    });

    it('rejects an empty replay response', async () => {
      vi.mocked(sessionReplay).mockResolvedValue({} as never);
      const session = new Session(mockClient);
      await session.start();
      await expect(session.replay()).rejects.toThrow('empty response');
    });

    it('polls on 404 until the replay is ready', async () => {
      vi.mocked(sessionReplay)
        .mockRejectedValueOnce(new NotteAPIError('/replay', 404, { message: 'Replay not found' }))
        .mockRejectedValueOnce(new NotteAPIError('/replay', 404, { detail: 'not ready' }))
        .mockResolvedValueOnce({ data: replays[0] } as never);
      const session = new Session(mockClient);
      await session.start();

      expect(await session.replay({ pollIntervalMs: 10 })).toEqual(replays[0]);
      expect(sessionReplay).toHaveBeenCalledTimes(3);
      expect(sleep).toHaveBeenCalledTimes(2);
      expect(sleep).toHaveBeenCalledWith(10);
    });

    it('throws when the API says the session is still active', async () => {
      vi.mocked(sessionReplay).mockRejectedValue(new NotteAPIError('/replay', 404, { message: 'Session is still active' }));
      const session = new Session(mockClient);
      await session.start();

      await expect(session.replay()).rejects.toThrow('Session session-123 is still active');
      expect(sleep).not.toHaveBeenCalled();
    });

    it('throws NotteTimeoutError when the deadline passes', async () => {
      vi.mocked(sessionReplay).mockRejectedValue(new NotteAPIError('/replay', 404, {}));
      const session = new Session(mockClient);
      await session.start();

      await expect(session.replay({ timeoutMs: 0, pollIntervalMs: 5 })).rejects.toBeInstanceOf(NotteTimeoutError);
      await expect(session.replay({ timeoutMs: 0, pollIntervalMs: 5 })).rejects.toThrow('not ready within 0ms');
      expect(sleep).not.toHaveBeenCalled();
    });

    it('does not poll when wait is false', async () => {
      const error = new NotteAPIError('/replay', 404, {});
      vi.mocked(sessionReplay).mockRejectedValue(error);
      const session = new Session(mockClient);
      await session.start();

      await expect(session.replay({ wait: false })).rejects.toBe(error);
      expect(sessionReplay).toHaveBeenCalledTimes(1);
    });

    it('rethrows non-404 errors immediately', async () => {
      const error = new NotteAPIError('/replay', 500, {});
      vi.mocked(sessionReplay).mockRejectedValue(error);
      const session = new Session(mockClient);
      await session.start();

      await expect(session.replay()).rejects.toBe(error);
      expect(sessionReplay).toHaveBeenCalledTimes(1);
    });
  });

  describe('downloadReplay', () => {
    let tempDir: string;

    beforeEach(async () => {
      tempDir = await mkdtemp(join(tmpdir(), 'notte-replay-'));
    });

    afterEach(async () => {
      vi.unstubAllGlobals();
      await rm(tempDir, { recursive: true, force: true });
    });

    it('writes the mp4 to the given path', async () => {
      vi.mocked(sessionReplay).mockResolvedValue({ data: replaysFixture() } as never);
      const fetchMock = vi.fn(async () => new Response(new Uint8Array([1, 2, 3])));
      vi.stubGlobal('fetch', fetchMock);
      const session = new Session(mockClient);
      await session.start();

      const target = join(tempDir, 'replay.mp4');
      expect(await session.downloadReplay(target)).toBe(target);
      expect(fetchMock).toHaveBeenCalledWith('https://example.com/replay.mp4');
      expect([...(await readFile(target))]).toEqual([1, 2, 3]);
    });

    it('throws when the replay has no mp4_url', async () => {
      vi.mocked(sessionReplay).mockResolvedValue({ data: { playlist_content: '#EXTM3U', expires_at: 'x' } } as never);
      const session = new Session(mockClient);
      await session.start();
      await expect(session.downloadReplay(join(tempDir, 'replay.mp4'))).rejects.toThrow('No mp4_url available for download');
    });

    function replaysFixture(): ReplayResponse {
      return { mp4_url: 'https://example.com/replay.mp4', expires_at: '2099-01-01T00:00:00Z' };
    }
  });

  describe('cookies', () => {
    let tempDir: string;
    const cookie: Cookie = { name: 'token', value: 'abc', domain: 'example.com', path: '/', httpOnly: false };

    beforeEach(async () => {
      tempDir = await mkdtemp(join(tmpdir(), 'notte-cookies-'));
      vi.mocked(sessionCookiesSet).mockResolvedValue({ data: { success: true, message: 'ok' } } as never);
      vi.mocked(sessionCookiesGet).mockResolvedValue({ data: { cookies: [cookie] } } as never);
    });

    afterEach(async () => {
      await rm(tempDir, { recursive: true, force: true });
    });

    it('sets and gets cookies', async () => {
      const session = new Session(mockClient);
      await session.start();
      expect(await session.setCookies([cookie])).toEqual({ success: true, message: 'ok' });
      expect(sessionCookiesSet).toHaveBeenCalledWith(expect.objectContaining({ body: { cookies: [cookie] } }));
      expect(await session.getCookies()).toEqual([cookie]);
    });

    it('sets cookies from a JSON file', async () => {
      const file = join(tempDir, 'cookies.json');
      await writeFile(file, JSON.stringify([cookie]));
      const session = new Session(mockClient);
      await session.start();
      await session.setCookiesFromFile(file);
      expect(sessionCookiesSet).toHaveBeenCalledWith(expect.objectContaining({ body: { cookies: [cookie] } }));
    });

    it('warns and continues when the cookie_file does not exist at start', async () => {
      const file = join(tempDir, 'missing.json');
      const session = new Session(mockClient, { cookie_file: file });
      await session.start();
      expect(sessionCookiesSet).not.toHaveBeenCalled();
      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining(`Cookie file ${file} not found`));
    });

    it('loads the cookie_file on start and appends the session cookies on stop', async () => {
      const file = join(tempDir, 'cookies.json');
      const existing: Cookie = { ...cookie, name: 'existing' };
      await writeFile(file, JSON.stringify([existing]));
      const session = new Session(mockClient, { cookie_file: file });

      await session.start();
      expect(sessionCookiesSet).toHaveBeenCalledWith(expect.objectContaining({ body: { cookies: [existing] } }));

      await session.stop();
      expect(sessionCookiesGet).toHaveBeenCalledTimes(1);
      expect(JSON.parse(await readFile(file, 'utf-8'))).toEqual([existing, cookie]);
      expect(session.isSessionActive()).toBe(false);
    });

    it('stops the remote session with close_reason error when cookie loading fails after start', async () => {
      const file = join(tempDir, 'broken.json');
      await writeFile(file, '{not json');
      const session = new Session(mockClient, { cookie_file: file });

      await expect(session.start()).rejects.toThrow();

      expect(sessionStop).toHaveBeenCalledWith(expect.objectContaining({ query: { close_reason: 'error' } }));
      expect(session.isSessionActive()).toBe(false);
    });

    it('stops the remote session when the cookie upload fails after start', async () => {
      const file = join(tempDir, 'cookies.json');
      await writeFile(file, JSON.stringify([cookie]));
      vi.mocked(sessionCookiesSet).mockRejectedValueOnce(new NotteAPIError('/sessions/x/cookies', 500, { message: 'boom' }));
      const session = new Session(mockClient, { cookie_file: file });

      await expect(session.start()).rejects.toBeInstanceOf(NotteAPIError);

      expect(sessionStop).toHaveBeenCalledWith(expect.objectContaining({ query: { close_reason: 'error' } }));
      expect(session.isSessionActive()).toBe(false);
    });

    it('creates the cookie_file on stop when it did not exist', async () => {
      const file = join(tempDir, 'new.json');
      const session = new Session(mockClient, { cookie_file: file });
      await session.start();
      await session.stop();
      expect(JSON.parse(await readFile(file, 'utf-8'))).toEqual([cookie]);
    });

    it('logs and still stops when saving cookies fails', async () => {
      vi.mocked(sessionCookiesGet).mockRejectedValue(new Error('cookies unavailable'));
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const session = new Session(mockClient, { cookie_file: join(tempDir, 'cookies.json') });
      await session.start();
      await session.stop();
      expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining('Error saving cookies'));
      expect(sessionStop).toHaveBeenCalled();
    });
  });

  describe('storage', () => {
    it('sends use_file_storage and binds the storage to the session id', async () => {
      const storage = { setSessionId: vi.fn(), forSession: vi.fn() } as unknown as RemoteFileStorage;
      vi.mocked(storage.forSession).mockReturnValue(storage);
      const session = new Session(mockClient, { storage, proxies: false });
      expect(session.storage).toBe(storage);

      await session.start();

      expect(sessionStart).toHaveBeenCalledWith(expect.objectContaining({ body: { proxies: false, use_file_storage: true } }));
      expect(vi.mocked(storage.forSession)).toHaveBeenCalledWith('session-123');
      expect(session.storage).toBe(storage);
    });
  });

  describe('observe', () => {
    const observation = { space: { description: '', interaction_actions: [] }, metadata: {} };

    beforeEach(() => {
      vi.mocked(pageObserve).mockResolvedValue({ data: observation } as never);
    });

    it('defaults to fast perception', async () => {
      const session = new Session(mockClient);
      await session.start();
      expect(await session.observe()).toEqual(observation);
      expect(pageObserve).toHaveBeenCalledWith(expect.objectContaining({ body: { perception_type: 'fast' } }));
    });

    it('keeps the legacy string signature', async () => {
      const session = new Session(mockClient);
      await session.start();
      await session.observe('deep');
      expect(pageObserve).toHaveBeenCalledWith(expect.objectContaining({ body: { perception_type: 'deep' } }));
    });

    it('accepts the full observe request and the session default perception type', async () => {
      const session = new Session(mockClient, { perception_type: 'deep' });
      await session.start();
      await session.observe({ instructions: 'click jobs', max_nb_actions: 5, perception_type: null });
      expect(pageObserve).toHaveBeenCalledWith(
        expect.objectContaining({ body: { instructions: 'click jobs', max_nb_actions: 5, perception_type: 'deep' } }),
      );
    });

    it('rejects when not started', async () => {
      await expect(new Session(mockClient).observe()).rejects.toThrow('Session not started');
    });
  });

  describe('debug info', () => {
    const debug: SessionDebugResponse = {
      debug_url: 'https://debug',
      ws: { cdp: 'wss://api.notte.cc/cdp', recording: 'wss://rec', logs: 'wss://logs' },
      tabs: [
        { metadata: { tab_id: 0, title: 'a', url: 'https://a' }, debug_url: 'https://a/debug', ws_url: 'wss://a' },
        { metadata: { tab_id: 1, title: 'b', url: 'https://b' }, debug_url: 'https://b/debug', ws_url: 'wss://b' },
      ],
    };

    beforeEach(() => {
      vi.mocked(sessionDebugInfo).mockResolvedValue({ data: debug } as never);
    });

    it('returns the debug info', async () => {
      const session = new Session(mockClient);
      await session.start();
      expect(await session.debugInfo()).toEqual(debug);
      expect(sessionDebugInfo).toHaveBeenCalledWith(expect.objectContaining({ path: { session_id: 'session-123' } }));
    });

    it('returns a tab from the debug info', async () => {
      const session = new Session(mockClient);
      await session.start();
      expect(await session.debugTabInfo()).toEqual(debug.tabs[0]);
      expect(await session.debugTabInfo(1)).toEqual(debug.tabs[1]);
      await expect(session.debugTabInfo(2)).rejects.toThrow('Tab 2 not found');
    });
  });

  describe('getScript', () => {
    it('requests a standalone workflow by default and works after stop', async () => {
      const code = { python_script: 'print(1)', json_actions: [] };
      vi.mocked(getSessionScript).mockResolvedValue({ data: code } as never);
      const session = new Session(mockClient);
      await session.start();
      await session.stop();

      expect(await session.getScript()).toEqual(code);
      expect(getSessionScript).toHaveBeenCalledWith(
        expect.objectContaining({ path: { session_id: 'session-123' }, query: { as_workflow: true } }),
      );

      await session.getScript({ as_workflow: false, infer_response_format: true });
      expect(getSessionScript).toHaveBeenLastCalledWith(
        expect.objectContaining({ query: { as_workflow: false, infer_response_format: true } }),
      );
    });
  });

  describe('getters', () => {
    it('should return null for getId when session not started', () => {
      expect(new Session(mockClient).getId()).toBeNull();
    });

    it('should return false for isSessionActive when session not started', () => {
      expect(new Session(mockClient).isSessionActive()).toBe(false);
    });

    it('should return null for getResponse when no operations performed', () => {
      expect(new Session(mockClient).getResponse()).toBeNull();
    });
  });

  describe('context manager', () => {
    it('stops with an error reason and preserves callback exceptions', async () => {
      vi.mocked(sessionStop).mockResolvedValue({
        data: sessionResponse({ status: 'closed', close_reason: 'error' }),
      } as never);
      const callbackError = new Error('callback failed');
      const session = new Session(mockClient);

      await expect(session.use(async () => {
        throw callbackError;
      })).rejects.toBe(callbackError);

      expect(sessionStop).toHaveBeenCalledWith(expect.objectContaining({ query: { close_reason: 'error' } }));
      expect(session.getResponse()?.close_reason).toBe('error');
      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('Session exiting because of exception'));
    });

    it('stops with the manual reason and returns the callback result', async () => {
      const session = new Session(mockClient);
      expect(await session.use(async s => s.getId())).toBe('session-123');
      expect(sessionStop).toHaveBeenCalledWith(expect.objectContaining({ query: { close_reason: 'manual' } }));
      expect(session.isSessionActive()).toBe(false);
    });

    it('propagates stop errors when the callback succeeded', async () => {
      vi.mocked(sessionStop).mockRejectedValue(new Error('stop failed'));
      await expect(new Session(mockClient).use(async () => 'ok')).rejects.toThrow('stop failed');
    });

    it('logs stop errors when the callback failed', async () => {
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      vi.mocked(sessionStop).mockRejectedValue(new Error('stop failed'));
      await expect(new Session(mockClient).use(async () => {
        throw new Error('callback failed');
      })).rejects.toThrow('callback failed');
      expect(errorSpy).toHaveBeenCalledWith('[Session] Failed to stop session after callback error:', expect.any(Error));
    });

    it('supports async iteration', async () => {
      const session = new Session(mockClient);
      for await (const active of session) {
        expect(active.isSessionActive()).toBe(true);
      }
      expect(session.isSessionActive()).toBe(false);
      expect(sessionStop).toHaveBeenCalledTimes(1);
    });
  });

  describe('viewer', () => {
    it('should open the viewer when open_viewer is true', async () => {
      vi.mocked(sessionStart).mockResolvedValue({
        data: sessionResponse({ viewer_url: 'https://viewer.notte.cc/session-123' }),
      } as never);

      const session = new Session(mockClient, { headless: true, open_viewer: true });
      await session.start();

      const startCall = vi.mocked(sessionStart).mock.calls[0][0] as { body: Record<string, unknown> };
      expect(startCall.body).toEqual({});
      expect(startCall.body).not.toHaveProperty('open_viewer');
      expect(openBrowser).toHaveBeenCalledWith('https://viewer.notte.cc/session-123');
    });

    it('should not open the viewer when open_viewer is false', async () => {
      vi.mocked(sessionStart).mockResolvedValue({
        data: sessionResponse({ viewer_url: 'https://viewer.notte.cc/session-123' }),
      } as never);

      const session = new Session(mockClient, { headless: true, open_viewer: false });
      await session.start();

      expect(openBrowser).not.toHaveBeenCalled();
    });

    it('should keep the session active when open_viewer is true but viewer_url is missing', async () => {
      const session = new Session(mockClient, { headless: true, open_viewer: true });
      await expect(session.start()).resolves.toBeUndefined();

      expect(session.getId()).toBe('session-123');
      expect(session.isSessionActive()).toBe(true);
      expect(openBrowser).not.toHaveBeenCalled();
      expect(warnSpy).toHaveBeenCalledWith('[Session] No viewer URL available; session started without opening a viewer.');
    });

    it('should throw when opening a viewer before session start', () => {
      expect(() => new Session(mockClient).viewer()).toThrow('Session not started');
    });

    it('should throw when manually opening a viewer without viewer_url', async () => {
      const session = new Session(mockClient);
      await session.start();
      expect(() => session.viewer()).toThrow('No viewer URL available for this session');
    });
  });
});

// Note: For comprehensive integration tests that test actual API interactions,
// see session.integration.test.ts which requires NOTTE_API_KEY environment variable.

describe('Session storage binding', () => {
  it('clones a storage already bound to another session instead of rebinding it', async () => {
    const storage = { forSession: vi.fn(), setSessionId: vi.fn() };
    const clone = { forSession: vi.fn(), setSessionId: vi.fn() };
    storage.forSession.mockReturnValue(clone);
    vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse({ session_id: 'session-b' }) } as never);

    const session = new Session(mockNotteClient(), { storage: storage as never });
    await session.start();

    expect(storage.forSession).toHaveBeenCalledWith('session-b');
    expect(storage.setSessionId).not.toHaveBeenCalled();
    expect(session.storage).toBe(clone);
    expect(sessionStart).toHaveBeenCalledWith(expect.objectContaining({ body: expect.objectContaining({ use_file_storage: true }) }));
  });
});
