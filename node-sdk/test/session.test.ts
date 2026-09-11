import { beforeEach, describe, it, expect, expectTypeOf, vi } from 'vitest';
import { Session } from '@/session';
import { NotteClient } from '@/client';
import { sessionStart, sessionStop } from '@/lib/client/sdk.gen';
import type {
  SessionOptions,
} from '@/index';
import { openBrowser } from '@/utils';

vi.mock('@/lib/client/sdk.gen', () => ({
  sessionStart: vi.fn(),
  sessionStop: vi.fn(),
  sessionStatus: vi.fn(),
  sessionCookiesSet: vi.fn(),
  sessionCookiesGet: vi.fn(),
  pageExecute: vi.fn(),
  pageObserve: vi.fn(),
  sessionReplay: vi.fn(),
  pageScrape: vi.fn(),
}));

vi.mock('@/utils', () => ({
  formatError: (error: unknown) => String(error),
  openBrowser: vi.fn(),
}));

describe('Session Unit Tests', () => {
  const mockClient = {
    getClient: vi.fn(() => ({})),
  } as unknown as NotteClient;

  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(mockClient.getClient).mockReturnValue({} as ReturnType<NotteClient['getClient']>);
  });

  describe('constructor', () => {
    it('should create session with default options', () => {
      const session = new Session(mockClient);
      expect(session).toBeDefined();
      expect(session.getId()).toBeNull();
      expect(session.isSessionActive()).toBe(false);
    });

    it('should create session with custom options', () => {
      const session = new Session(mockClient, { headless: true });
      expect(session).toBeDefined();
      expect(session.getId()).toBeNull();
      expect(session.isSessionActive()).toBe(false);
    });

    it('should accept open_viewer as a local option', () => {
      const session = new Session(mockClient, { headless: true, open_viewer: true });
      expect(session).toBeDefined();
      expect(session.getId()).toBeNull();
      expect(session.isSessionActive()).toBe(false);
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
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      vi.mocked(sessionStart).mockResolvedValue({
        data: { session_id: 'session-123' },
      } as any);
      const session = new Session(mockClient, { headless: true });

      await session.start();

      expect(sessionStart).toHaveBeenCalledWith(expect.objectContaining({
        body: {},
      }));
      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('`headless: true` is deprecated'));
    });

    it('should reject deprecated headless false when starting with a migration error', async () => {
      const session = new Session(mockClient, { headless: false });

      await expect(session.start()).rejects.toThrow(
        'Remote `headless: false` is no longer supported.'
      );
      expect(sessionStart).not.toHaveBeenCalled();
    });
  });

  describe('getters', () => {
    it('should return null for getId when session not started', () => {
      const session = new Session(mockClient);
      expect(session.getId()).toBeNull();
    });

    it('should return false for isSessionActive when session not started', () => {
      const session = new Session(mockClient);
      expect(session.isSessionActive()).toBe(false);
    });

    it('should return null for getResponse when no operations performed', () => {
      const session = new Session(mockClient);
      expect(session.getResponse()).toBeNull();
    });
  });

  describe('context manager', () => {
    it('stops with an error reason and preserves callback exceptions', async () => {
      vi.mocked(sessionStart).mockResolvedValue({
        data: { session_id: 'session-123' },
      } as any);
      vi.mocked(sessionStop).mockResolvedValue({
        data: { session_id: 'session-123', status: 'closed', close_reason: 'error' },
      } as any);
      const callbackError = new Error('callback failed');
      const session = new Session(mockClient);

      await expect(session.use(async () => {
        throw callbackError;
      })).rejects.toBe(callbackError);

      expect(sessionStop).toHaveBeenCalledWith(expect.objectContaining({
        query: { close_reason: 'error' },
      }));
      expect(session.getResponse()?.close_reason).toBe('error');
    });
  });

  describe('viewer', () => {
    let warnSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
      warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    });

    it('should open the viewer when open_viewer is true', async () => {
      vi.mocked(sessionStart).mockResolvedValue({
        data: {
          session_id: 'session-123',
          viewer_url: 'https://viewer.notte.cc/session-123',
        },
      } as any);

      const session = new Session(mockClient, { headless: true, open_viewer: true });
      await session.start();

      const startCall = vi.mocked(sessionStart).mock.calls[0][0] as any;
      expect(startCall.body).toEqual({});
      expect(startCall.body).not.toHaveProperty('open_viewer');
      expect(openBrowser).toHaveBeenCalledWith('https://viewer.notte.cc/session-123');
    });

    it('should not open the viewer when open_viewer is false', async () => {
      vi.mocked(sessionStart).mockResolvedValue({
        data: {
          session_id: 'session-123',
          viewer_url: 'https://viewer.notte.cc/session-123',
        },
      } as any);

      const session = new Session(mockClient, { headless: true, open_viewer: false });
      await session.start();

      expect(openBrowser).not.toHaveBeenCalled();
    });

    it('should keep the session active when open_viewer is true but viewer_url is missing', async () => {
      vi.mocked(sessionStart).mockResolvedValue({
        data: {
          session_id: 'session-123',
        },
      } as any);

      const session = new Session(mockClient, { headless: true, open_viewer: true });
      await expect(session.start()).resolves.toBeUndefined();

      expect(session.getId()).toBe('session-123');
      expect(session.isSessionActive()).toBe(true);
      expect(openBrowser).not.toHaveBeenCalled();
      expect(warnSpy).toHaveBeenCalledWith('[Session] No viewer URL available; session started without opening a viewer.');
    });

    it('should throw when opening a viewer before session start', () => {
      const session = new Session(mockClient);

      expect(() => session.viewer()).toThrow('Session not started');
    });

    it('should throw when manually opening a viewer without viewer_url', async () => {
      vi.mocked(sessionStart).mockResolvedValue({
        data: {
          session_id: 'session-123',
        },
      } as any);

      const session = new Session(mockClient);
      await session.start();

      expect(() => session.viewer()).toThrow('No viewer URL available for this session');
    });
  });
});

// Note: For comprehensive integration tests that test actual API interactions,
// see session.integration.test.ts which requires NOTTE_API_KEY environment variable.
