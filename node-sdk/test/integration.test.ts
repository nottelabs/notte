import { describe, it, expect } from 'vitest';
import { NotteClient } from '@/client';
import { AuthenticationError } from '@/errors';
import { config } from 'dotenv';
config();

describe('Integration Tests', () => {

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
