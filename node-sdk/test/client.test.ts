import { describe, it, expect, beforeEach, vi } from 'vitest';
import { NotteClient } from '@/client';
import { client } from '@/lib/client/client.gen';

// Mock the generated client
vi.mock('@/lib/client/client.gen', () => ({
  client: {
    setConfig: vi.fn(),
    interceptors: {
      request: {
        use: vi.fn()
      },
      response: {
        use: vi.fn()
      }
    }
  }
}));

describe('NotteClient', () => {
  let notteClient: NotteClient;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('constructor', () => {
    it('should create client with default config', () => {
      notteClient = new NotteClient({ apiKey: 'test-key' }) // pragma: allowlist secret

      expect(client.setConfig).toHaveBeenCalledWith(
        expect.objectContaining({ baseUrl: process.env.NOTTE_API_URL || 'https://api.notte.cc', redirect: 'manual' })
      );
    });

    it('should create client with custom baseUrl', () => {
      const config = {
        baseUrl: 'https://custom.api.com',
        apiKey: 'test-key' // pragma: allowlist secret
      };

      notteClient = new NotteClient(config);

      expect(client.setConfig).toHaveBeenCalledWith(
        expect.objectContaining({ baseUrl: 'https://custom.api.com', redirect: 'manual' })
      );
      expect(client.interceptors.request.use).toHaveBeenCalled();
    });

    it('should use NOTTE_API_URL env var when no baseUrl is provided', () => {
      const original = process.env.NOTTE_API_URL;
      try {
        process.env.NOTTE_API_URL = 'https://us-staging.notte.cc';
        vi.clearAllMocks();

        notteClient = new NotteClient({ apiKey: 'test-key' }); // pragma: allowlist secret

        expect(client.setConfig).toHaveBeenCalledWith(
          expect.objectContaining({ baseUrl: 'https://us-staging.notte.cc', redirect: 'manual' })
        );
      } finally {
        if (original === undefined) {
          delete process.env.NOTTE_API_URL;
        } else {
          process.env.NOTTE_API_URL = original;
        }
      }
    });

    it('should prefer explicit baseUrl over NOTTE_API_URL env var', () => {
      const original = process.env.NOTTE_API_URL;
      try {
        process.env.NOTTE_API_URL = 'https://us-staging.notte.cc';
        vi.clearAllMocks();

        notteClient = new NotteClient({ apiKey: 'test-key', baseUrl: 'https://custom.api.com' }); // pragma: allowlist secret

        expect(client.setConfig).toHaveBeenCalledWith(
          expect.objectContaining({ baseUrl: 'https://custom.api.com', redirect: 'manual' })
        );
      } finally {
        if (original === undefined) {
          delete process.env.NOTTE_API_URL;
        } else {
          process.env.NOTTE_API_URL = original;
        }
      }
    });

    it('should fallback to https://api.notte.cc when no baseUrl or env var is set', () => {
      const original = process.env.NOTTE_API_URL;
      try {
        delete process.env.NOTTE_API_URL;
        vi.clearAllMocks();

        notteClient = new NotteClient({ apiKey: 'test-key' }); // pragma: allowlist secret

        expect(client.setConfig).toHaveBeenCalledWith(
          expect.objectContaining({ baseUrl: 'https://api.notte.cc', redirect: 'manual' })
        );
      } finally {
        if (original === undefined) {
          delete process.env.NOTTE_API_URL;
        } else {
          process.env.NOTTE_API_URL = original;
        }
      }
    });

    it('should throw error when no API key is provided', () => {
      const original = process.env.NOTTE_API_KEY;
      try {
        delete process.env.NOTTE_API_KEY;

        expect(() => new NotteClient({})).toThrow('API key is required');
      } finally {
        if (original === undefined) {
          delete process.env.NOTTE_API_KEY;
        } else {
          process.env.NOTTE_API_KEY = original;
        }
      }
    });

    it('should read NOTTE_API_KEY from env when not passed in config', () => {
      const original = process.env.NOTTE_API_KEY;
      try {
        process.env.NOTTE_API_KEY = 'env-api-key'; // pragma: allowlist secret
        vi.clearAllMocks();

        notteClient = new NotteClient();

        expect(client.interceptors.request.use).toHaveBeenCalled();
        expect(notteClient.getConfig().apiKey).toBe('env-api-key'); // pragma: allowlist secret
      } finally {
        if (original === undefined) {
          delete process.env.NOTTE_API_KEY;
        } else {
          process.env.NOTTE_API_KEY = original;
        }
      }
    });
  });

  describe('Session', () => {
    beforeEach(() => {
      notteClient = new NotteClient({ apiKey: 'test-key' }) // pragma: allowlist secret;
    });

    it('should create a new session', () => {
      const session = notteClient.Session();
      expect(session).toBeDefined();
      expect(session.constructor.name).toBe('Session');
    });

    it('should create session with options', () => {
      const session = notteClient.Session({ idle_timeout_minutes: 15 });
      expect(session).toBeDefined();
    });
  });

  describe('Agent', () => {
    beforeEach(() => {
      notteClient = new NotteClient({ apiKey: 'test-key' }) // pragma: allowlist secret;
    });

    it('should create a new agent', () => {
      const session = notteClient.Session();
      // Mock the session to have an ID for testing
      Object.defineProperty(session, 'sessionId', {
        value: 'test-session-id',
        writable: false
      });
      Object.defineProperty(session, 'getId', {
        value: () => 'test-session-id',
        writable: false
      });

      const agent = notteClient.Agent({ session, max_steps: 5 });

      expect(agent).toBeDefined();
      expect(agent.constructor.name).toBe('Agent');
    });
  });

  describe('getClient', () => {
    it('should return the configured client', () => {
      notteClient = new NotteClient({ apiKey: 'test-key' }) // pragma: allowlist secret;
      const clientInstance = notteClient.getClient();

      expect(clientInstance).toBe(client);
    });
  });

  describe('getConfig', () => {
    it('should return the client configuration', () => {
      const config = {
        baseUrl: 'https://test.api.com',
        apiKey: 'test-key' // pragma: allowlist secret
      };

      notteClient = new NotteClient(config);
      const returnedConfig = notteClient.getConfig();

      expect(returnedConfig).toEqual(config);
    });
  });
});
