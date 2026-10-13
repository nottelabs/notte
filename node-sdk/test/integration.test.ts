import { describe, it, expect, vi } from 'vitest';
import { NotteClient } from '@/client';
import { AuthenticationError } from '@/errors';
import { config } from 'dotenv';
config();

describe('Integration Tests', () => {
  describe('NotteClient with Session and Agent', () => {
    it('should create client, session, and agent together', () => {
      const notte = new NotteClient();

      const session = notte.Session({ proxies: false, idle_timeout_minutes: 1 });
      // Mock the session to have an ID for testing
      Object.defineProperty(session, 'sessionId', {
        value: 'test-session-id',
        writable: false
      });
      Object.defineProperty(session, 'getId', {
        value: () => 'test-session-id',
        writable: false
      });

      const agent = notte.Agent({ session, max_steps: 8 });

      expect(session).toBeDefined();
      expect(agent).toBeDefined();
      expect(session.constructor.name).toBe('Session');
      expect(agent.constructor.name).toBe('Agent');
    });

    it('should mirror Python SDK usage pattern', () => {
      // This test demonstrates the TypeScript equivalent of:
      // from notte_sdk import NotteClient
      // notte = NotteClient()
      // with notte.Session(idle_timeout_minutes=2) as session:
      //     agent = notte.Agent(session=session, max_steps=10)
      //     response = agent.run(task="Find the best italian restaurant in SF")

      const notte = new NotteClient({ apiKey: 'test-key' }); // pragma: allowlist secret

      // TypeScript doesn't have "with" statement, but we provide async iterator pattern
      const session = notte.Session({ proxies: false, idle_timeout_minutes: 2 });
      // Mock the session to have an ID for testing
      Object.defineProperty(session, 'sessionId', {
        value: 'test-session-id',
        writable: false
      });
      Object.defineProperty(session, 'getId', {
        value: () => 'test-session-id',
        writable: false
      });

      const agent = notte.Agent({ session, max_steps: 10 });

      expect(session).toBeDefined();
      expect(agent).toBeDefined();

      // The usage would be:
      // await session.use(async (session) => {
      //   const agent = notte.Agent({ session, max_steps: 10 });
      //   const response = await agent.run("Find the best italian restaurant in SF");
      // });
    });
  });

  describe('Error handling', () => {
    it('should handle missing configuration gracefully', () => {
      // Temporarily unset the environment variable
      const originalApiKey = process.env.NOTTE_API_KEY;
      delete process.env.NOTTE_API_KEY;

      expect(() => {
        new NotteClient();
      }).toThrow(AuthenticationError);
      expect(() => {
        new NotteClient();
      }).toThrow('NOTTE_API_KEY needs to be provided');

      // Restore the original environment variable
      if (originalApiKey) {
        process.env.NOTTE_API_KEY = originalApiKey;
      }
    });
  });
});
