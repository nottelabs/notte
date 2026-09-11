/** Mirrors `tests/integration/sdk/test_interaction.py`: special action validation. */
import { beforeEach, describe, it, expect } from 'vitest';
import { NotteClient } from '@/client';
import { NotteAPIError } from '@/errors';
import { actions, type ExecuteAction } from '@/actions';
import type { ApiExecutionResponse } from '@/lib/client/types.gen';

import { config } from 'dotenv';
config();

describe('Interaction Integration Tests', () => {
  let client: NotteClient;

  beforeEach(() => {
    const apiKey = process.env.NOTTE_API_KEY;
    if (!apiKey) {
      throw new Error('NOTTE_API_KEY environment variable is required for integration tests');
    }
    client = new NotteClient({ apiKey, baseUrl: process.env.NOTTE_API_URL || 'https://api.notte.cc' });
  });

  it('validates special action parameters', { timeout: 90_000 }, async () => {
    await client.Session({ proxies: false, open_viewer: false }).use(async page => {
      await page.execute(actions.goto({ url: 'https://github.com/' }));
      await page.observe({ perception_type: 'fast' });

      // goto requires a url: the API rejects the request with a validation error
      const gotoError = await page.execute({ type: 'goto' } as unknown as ExecuteAction).catch((e: unknown) => e);
      expect(gotoError).toBeInstanceOf(NotteAPIError);
      expect((gotoError as NotteAPIError).statusCode).toBe(422);

      // wait requires time_ms
      const waitError = await page.execute({ type: 'wait' } as unknown as ExecuteAction).catch((e: unknown) => e);
      expect(waitError).toBeInstanceOf(NotteAPIError);
      expect((waitError as NotteAPIError).statusCode).toBe(422);

      const checkFailure = (result: ApiExecutionResponse) => {
        expect(result.success).toBe(false);
        expect(result.message).toContain("Action with id 'X1' is invalid");
        expect(result.exception_detail?.error_type).toBeTruthy();
      };

      // invalid interaction action, both call styles
      checkFailure(await page.execute({ type: 'click', id: 'X1' }, { raiseOnFailure: false }));
      checkFailure(await page.execute(actions.click({ id: 'X1' }), { raiseOnFailure: false }));
    });
  });
});
