/** `evaluateJs()` and `fetch()` against a real page. */
import { beforeEach, describe, it, expect } from 'vitest';
import { NotteClient } from '@/client';
import { ActionExecutionError } from '@/errors';
import { actions } from '@/actions';
import { PageFetchResponse } from '@/page-fetch';

import { config } from 'dotenv';
config();

describe('evaluateJs and fetch Integration Tests', () => {
  let client: NotteClient;

  beforeEach(() => {
    const apiKey = process.env.NOTTE_API_KEY;
    if (!apiKey) {
      throw new Error('NOTTE_API_KEY environment variable is required for integration tests');
    }
    client = new NotteClient({ apiKey, baseUrl: process.env.NOTTE_API_URL || 'https://api.notte.cc' });
  });

  it('evaluates JavaScript and returns the stringified value', { timeout: 90_000 }, async () => {
    await client.Session({ proxies: false, open_viewer: false }).use(async session => {
      await session.execute(actions.goto({ url: 'https://example.com' }));

      expect(await session.evaluateJs('1 + 1')).toBe('2');
      expect(await session.evaluateJs('document.title')).toBe('Example Domain');
      expect(JSON.parse(await session.evaluateJs('({ a: [1, 2] })'))).toEqual({ a: [1, 2] });
      expect(await session.evaluateJs('(async () => { await new Promise(r => setTimeout(r, 10)); return "done"; })()')).toBe('done');

      const envelope = await session.evaluateJs('notAFunction()', { raiseOnFailure: false });
      expect(envelope.success).toBe(false);
      expect(envelope.message).toContain('notAFunction is not defined');

      await expect(session.evaluateJs('notAFunction()')).rejects.toBeInstanceOf(ActionExecutionError);
    });
  });

  it('fetches from inside the page with the page cookies and follows redirects', { timeout: 90_000 }, async () => {
    await client.Session({ proxies: false, open_viewer: false }).use(async session => {
      await session.execute(actions.goto({ url: 'https://en.wikipedia.org/wiki/Main_Page' }));

      const response = await session.fetch('/api/rest_v1/page/summary/Main_Page', { params: { redirect: 'false' } });
      expect(response).toBeInstanceOf(PageFetchResponse);
      expect(response.ok).toBe(true);
      expect(response.status).toBe(200);
      expect(response.url).toContain('wikipedia.org/api/rest_v1/page/summary/Main_Page');
      expect(response.headers.get('content-type')).toContain('application/json');
      const summary = (await response.json()) as { title?: string };
      expect(summary.title).toBeTruthy();

      const missing = await session.fetch('/api/rest_v1/page/summary/This_Page_Should_Not_Exist_' + Date.now());
      expect(missing.ok).toBe(false);
      expect(missing.status).toBe(404);
      expect(() => missing.raiseForStatus()).toThrow('404 Client Error');
    });
  });
});
