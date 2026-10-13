/**
 * Mirrors `tests/integration/sdk/test_error_serialization.py`: end-to-end
 * checks of the structured exception wire (`exception_detail`). The API
 * serialises failures with `SerializedError` so the client rehydrates the
 * concrete error type, its per-audience messages and retry/notify flags.
 */
import { beforeEach, describe, it, expect } from 'vitest';
import { NotteClient } from '@/client';
import { ActionExecutionError, NotteError } from '@/errors';
import { actions } from '@/actions';

import { config } from 'dotenv';
config();

describe('Error Serialization Integration Tests', () => {
  let client: NotteClient;

  beforeEach(() => {
    const apiKey = process.env.NOTTE_API_KEY;
    if (!apiKey) {
      throw new Error('NOTTE_API_KEY environment variable is required for integration tests');
    }
    client = new NotteClient({ apiKey, baseUrl: process.env.NOTTE_API_URL || 'https://api.notte.cc' });
  });

  it('rehydrates the concrete exception over the wire', { timeout: 90_000 }, async () => {
    await client.Session({ proxies: false, open_viewer: false }).use(async page => {
      await page.execute(actions.goto({ url: 'https://www.example.com' }));
      await page.observe({ perception_type: 'fast' });

      // non-raising path: the structured detail crosses the wire and names the concrete class
      const result = await page.execute(actions.click({ id: 'B999' }), { raiseOnFailure: false });
      expect(result.success).toBe(false);
      expect(result.exception_detail).toBeTruthy();
      expect(result.exception_detail?.error_type).toBe('InvalidActionError');
      expect(result.exception_detail?.dev_message).toContain('B999');

      // raising path: remote callers get the typed error with the action-specific reason intact
      const error = await page.execute(actions.click({ id: 'B999' })).catch((e: unknown) => e);
      expect(error).toBeInstanceOf(ActionExecutionError);
      expect((error as ActionExecutionError).errorType).toBe('InvalidActionError');
      expect((error as ActionExecutionError).devMessage).toContain('B999');
      expect((error as Error).message).toContain('B999');

      // evaluate_js failure: the JS reason must reach the caller. Before the
      // eval-js fix is deployed the server reports it without an exception
      // (SDK message fallback); after, as a typed ActionExecutionError. Both
      // are NotteError and both carry the reason.
      const jsError = await page.execute(actions.evaluateJs({ code: 'notAFunction()' })).catch((e: unknown) => e);
      expect(jsError).toBeInstanceOf(NotteError);
      expect(jsError).toBeInstanceOf(ActionExecutionError);
      expect((jsError as Error).message).toContain('JavaScript evaluation failed');
      expect((jsError as Error).message).toContain('notAFunction is not defined');
    });
  });
});
