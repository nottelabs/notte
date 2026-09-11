/** Mirrors `tests/integration/sdk/test_sessions.py` plus the session lifecycle helpers. */
import { describe, it, expect, beforeEach } from 'vitest';
import { NotteClient } from '@/client';
import { NotteTimeoutError } from '@/errors';
import { actions, type ExecuteAction } from '@/actions';

// Load environment variables
import { config } from 'dotenv';
config();

describe('Session Integration Tests', () => {
  let client: NotteClient;

  beforeEach(() => {
    const apiKey = process.env.NOTTE_API_KEY;
    if (!apiKey) {
      throw new Error('NOTTE_API_KEY environment variable is required for integration tests');
    }
    client = new NotteClient({ apiKey, baseUrl: process.env.NOTTE_API_URL || 'https://api.notte.cc' });
  });

  describe('Basic Session Operations', () => {
    it('should start and stop a session', async () => {
      const session = client.Session({ proxies: false });
      await session.start();
      try {
        expect(session.getResponse()?.status).toBe('active');
        expect(session.getId()).toBeDefined();
        expect(session.isSessionActive()).toBe(true);
      } finally {
        await session.stop();
      }
      expect(session.getResponse()?.status).toBe('closed');
      expect(session.getId()).toBeNull();
    });

    it('should create session with factory method', async () => {
      const session = client.Session({ proxies: false, headless: true });

      await session.use(async s => {
        expect(s.getId()).not.toBeNull();
        const status = await s.status();
        expect(status.status).toBe('active');
      });

      expect(session.getResponse()?.status).toBe('closed');
    });

    it('should create session with proxy settings', async () => {
      const session = client.Session({ proxies: true });

      await session.use(async s => {
        const status = await s.status();
        expect(status.status).toBe('active');
      });

      expect(session.getResponse()).not.toBeNull();
    });

    it('should create session with viewport settings', async () => {
      const session = client.Session({ proxies: false, viewport_height: 100, viewport_width: 100 });

      await session.use(async s => {
        const status = await s.status();
        expect(status.status).toBe('active');
      });

      expect(session.getResponse()).not.toBeNull();
    });

    it.each(['chrome', 'chromium'] as const)('should work with the %s browser type', async browserType => {
      await client.Session({ proxies: false, open_viewer: false, browser_type: browserType }).use(async session => {
        expect(session.getId()).not.toBeNull();
        const status = await session.status();
        expect(status.status).toBe('active');
      });
    });
  });

  describe('Session Replay', () => {
    it('polls for the replay after stop and can download it', { timeout: 300_000 }, async () => {
      const session = client.Session({ proxies: false, idle_timeout_minutes: 1 });
      await session.use(async s => {
        await s.execute(actions.goto({ url: 'https://example.com' }));
      });

      // Recordings are finalized only after the browser session is closed; replay() polls on 404.
      const replay = await session.replay();
      expect(replay.expires_at).toBeTruthy();
      expect(Boolean(replay.mp4_url || replay.playlist_content)).toBe(true);
    });

    it('reports the session as still active before stop', async () => {
      await client.Session({ proxies: false, idle_timeout_minutes: 1 }).use(async session => {
        await session.execute(actions.goto({ url: 'https://example.com' }));
        const error = await session.replay({ timeoutMs: 1_000, pollIntervalMs: 200 }).catch((e: unknown) => e);
        expect(error).toBeInstanceOf(Error);
        // either the API flags the active session or the short deadline passes
        const message = (error as Error).message;
        expect(message.includes('still active') || error instanceof NotteTimeoutError).toBe(true);
      });
    });
  });

  describe('Page Operations', () => {
    it('should execute goto action and observe page', { timeout: 60_000 }, async () => {
      await client.Session({ proxies: false, idle_timeout_minutes: 1 }).use(async session => {
        const executeResult = await session.execute(actions.goto({ url: 'https://www.ecosia.org' }));
        expect(executeResult.success).toBe(true);
        expect(executeResult.action.type).toBe('goto');

        const observeResult = await session.observe('fast');
        expect(observeResult.space).toBeDefined();
        expect(observeResult.space.description).toBeDefined();
        expect(observeResult.space.interaction_actions).toBeDefined();

        const deep = await session.observe({ perception_type: 'fast', max_nb_actions: 5 });
        expect(deep.space.interaction_actions).toBeDefined();
      });
    });

    it('exposes debug info and the workflow script', { timeout: 60_000 }, async () => {
      const session = client.Session({ proxies: false, idle_timeout_minutes: 1 });
      await session.use(async s => {
        await s.execute(actions.goto({ url: 'https://example.com' }));
        const debug = await s.debugInfo();
        expect(debug.ws.cdp).toMatch(/^wss?:\/\//);
        expect(debug.tabs.length).toBeGreaterThan(0);
        const tab = await s.debugTabInfo(0);
        expect(tab.ws_url).toBeTruthy();
      });
      const script = await session.getScript();
      expect(typeof script.python_script).toBe('string');
    });
  });

  describe('Action Validation', () => {
    it('should validate action parameters', { timeout: 60_000 }, async () => {
      await client.Session({ proxies: false }).use(async session => {
        await session.execute(actions.goto({ url: 'https://github.com/' }));
        await session.observe('fast');

        // goto requires a url: the API rejects the request
        await expect(session.execute({ type: 'goto' } as unknown as ExecuteAction)).rejects.toThrow();
        // wait requires time_ms
        await expect(session.execute({ type: 'wait' } as unknown as ExecuteAction)).rejects.toThrow();

        // invalid element id with raiseOnFailure=false (both call styles)
        const result = await session.execute(actions.click({ id: 'X1' }), { raiseOnFailure: false });
        expect(result.success).toBe(false);
        expect(result.message).toContain("Action with id 'X1' is invalid");

        const legacy = await session.execute({ type: 'click', id: 'X1' }, false);
        expect(legacy.success).toBe(false);
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle session not started errors', async () => {
      const session = client.Session({ proxies: false });

      await expect(session.status()).rejects.toThrow('Session not started');
      await expect(session.execute(actions.goto({ url: 'https://example.com' }))).rejects.toThrow('Session not started');
      await expect(session.observe()).rejects.toThrow('Session not started');
      await expect(session.getCookies()).rejects.toThrow('Session not started');
      await expect(session.cdpUrl()).rejects.toThrow('Session not started');
      await expect(session.replay()).rejects.toThrow('Session not started');
    });

    it('should handle already active session error', async () => {
      const session = client.Session({ proxies: false });
      await session.start();
      try {
        await expect(session.start()).rejects.toThrow('Session is already active');
      } finally {
        await session.stop();
      }
    });

    it('tolerates stopping a session twice', async () => {
      const session = client.Session({ proxies: false });
      await session.start();
      await session.stop();
      await expect(session.stop()).resolves.toBeUndefined();
    });
  });

  describe('Context Manager Pattern', () => {
    it('should automatically start and stop session', async () => {
      const session = client.Session({ proxies: false });

      const result = await session.use(async s => {
        expect(s.isSessionActive()).toBe(true);
        expect(s.getId()).not.toBeNull();
        return 'test-result';
      });

      expect(result).toBe('test-result');
      expect(session.isSessionActive()).toBe(false);
    });

    it('should stop session with the error reason if callback throws', async () => {
      const session = client.Session({ proxies: false });

      await expect(session.use(async () => {
        throw new Error('Test error');
      })).rejects.toThrow('Test error');

      expect(session.isSessionActive()).toBe(false);
      expect(session.getResponse()?.status).toBe('closed');
      expect(session.getResponse()?.close_reason).toBe('error');
    });
  });

  describe('Async Iterator Pattern', () => {
    it('should support async iteration', async () => {
      const session = client.Session({ proxies: false });

      for await (const activeSession of session) {
        expect(activeSession.isSessionActive()).toBe(true);
        expect(activeSession.getId()).not.toBeNull();
        break; // Exit after first iteration
      }

      expect(session.isSessionActive()).toBe(false);
    });
  });
});
