/**
 * Session steps, page by page: `GET /sessions/{session_id}/steps?cursor=...&limit=...`.
 * Mirrors `tests/sdk/test_session_steps.py`, on `client.sessions` and on a session object.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NotteClient } from '@/client';
import { NotteAPIError } from '@/errors';
import type { SessionStep } from '@/session-steps';

const BASE = 'https://api.notte.cc';
const STEPS_PATH = '/sessions/s-1/steps';
// Opaque: characters that need URL encoding must come back to the API unchanged.
const CURSOR_2 = 'c2+/=&x';
const CURSOR_3 = 'c3';
const STEP = { type: 'execution_result', value: { action: { type: 'goto', url: 'https://example.com' } } };
type Page = { steps?: SessionStep[]; next_cursor?: string | null };
const PAGES = new Map<string | null, Page>([
  [null, { steps: [{ ...STEP, n: 1 }, { ...STEP, n: 2 }], next_cursor: CURSOR_2 }],
  [CURSOR_2, { steps: [{ ...STEP, n: 3 }], next_cursor: CURSOR_3 }],
  [CURSOR_3, { steps: [{ ...STEP, n: 4 }], next_cursor: null }],
]);

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'content-type': 'application/json' },
});

describe('session steps', () => {
  let calls: URL[];
  let byCursor: Map<string | null, Page>;
  let expired: Set<string>;
  let client: NotteClient;

  beforeEach(() => {
    vi.stubEnv('NOTTE_SDK_DISABLE_VERSION_CHECK', '1');
    vi.spyOn(console, 'info').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    calls = [];
    byCursor = PAGES;
    expired = new Set();
    // The API: the page of the request's cursor, or a 400 for an expired cursor.
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
      const url = new URL(request.url);
      if (url.pathname === '/sessions/start') {
        return json({ session_id: 's-1', status: 'active', viewer_url: 'https://viewer.example/s-1' });
      }
      if (request.method === 'DELETE') return json({ session_id: 's-1', status: 'closed' });
      expect(request.method).toBe('GET');
      expect(url.origin + url.pathname).toBe(BASE + STEPS_PATH);
      calls.push(url);
      const cursor = url.searchParams.get('cursor');
      if (cursor !== null && expired.has(cursor)) return json({ detail: 'Invalid or expired cursor' }, 400);
      const page = byCursor.get(cursor);
      if (!page) throw new Error(`Unexpected cursor: ${cursor}`);
      return json(page);
    }));
    client = new NotteClient({ apiKey: 'test-key', baseUrl: BASE }); // pragma: allowlist secret (test fixture)
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks(); });

  const queries = () => calls.map(url => Object.fromEntries(url.searchParams));
  const numbers = (steps: SessionStep[]) => steps.map(step => step.n);
  const collect = async (steps: AsyncIterable<SessionStep>) => {
    const out: SessionStep[] = [];
    for await (const step of steps) out.push(step);
    return out;
  };

  // One page

  it('returns one page', async () => {
    const page = await client.sessions.steps('s-1');
    expect(page).toEqual({ steps: PAGES.get(null)!.steps, next_cursor: CURSOR_2 });
    // No cursor and no limit: the API's first page with its default size.
    expect(queries()).toEqual([{}]);
  });

  it('sends the cursor back unchanged for the next page', async () => {
    const page = await client.sessions.steps('s-1', { cursor: CURSOR_2, limit: 1 });
    expect(page).toEqual(PAGES.get(CURSOR_2));
    expect(queries()).toEqual([{ cursor: CURSOR_2, limit: '1' }]);
  });

  // Several pages

  it('iterSteps follows next_cursor', async () => {
    expect(numbers(await collect(client.sessions.iterSteps('s-1')))).toEqual([1, 2, 3, 4]);
    expect(queries()).toEqual([{}, { cursor: CURSOR_2 }, { cursor: CURSOR_3 }]);
  });

  it('iterSteps reads pages as it goes', async () => {
    const steps = client.sessions.iterSteps('s-1');
    expect(calls).toHaveLength(0);
    expect((await steps.next()).value?.n).toBe(1);
    expect((await steps.next()).value?.n).toBe(2);
    expect(calls).toHaveLength(1);
    expect((await steps.next()).value?.n).toBe(3);
    expect(calls).toHaveLength(2);
  });

  // Empty

  it.each([
    ['explicit', { steps: [], next_cursor: null }],
    ['defaults', {}],
  ])('handles an empty session (%s)', async (_, payload) => {
    byCursor = new Map([[null, payload]]);
    expect(await collect(client.sessions.iterSteps('s-1'))).toEqual([]);
    expect(queries()).toEqual([{}]);
    expect(await client.sessions.steps('s-1')).toEqual({ steps: [], next_cursor: null });
  });

  it('continues past an empty page that has a cursor', async () => {
    byCursor = new Map([[null, { steps: [], next_cursor: 'more' }], ['more', { steps: [{ ...STEP, n: 1 }], next_cursor: null }]]);
    expect(numbers(await collect(client.sessions.iterSteps('s-1')))).toEqual([1]);
    expect(queries()).toEqual([{}, { cursor: 'more' }]);
  });

  // Limit

  it('sends the limit on every page', async () => {
    await client.sessions.steps('s-1', { limit: 7 });
    expect(queries()).toEqual([{ limit: '7' }]);
    calls = [];
    await collect(client.sessions.iterSteps('s-1', { limit: 7 }));
    expect(queries()).toEqual([{ limit: '7' }, { cursor: CURSOR_2, limit: '7' }, { cursor: CURSOR_3, limit: '7' }]);
  });

  // A cursor that is no longer valid: 400, restart from the first page

  it('throws the 400 for an expired cursor', async () => {
    expired.add(CURSOR_2);
    const error = await client.sessions.steps('s-1', { cursor: CURSOR_2 }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(NotteAPIError);
    expect((error as NotteAPIError).statusCode).toBe(400);
  });

  it('iterSteps throws after the steps it yielded, then a new iteration reads from the first page', async () => {
    expired.add(CURSOR_2);
    const got: unknown[] = [];
    const error = await (async () => {
      for await (const step of client.sessions.iterSteps('s-1')) got.push(step.n);
    })().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(NotteAPIError);
    expect((error as NotteAPIError).statusCode).toBe(400);
    // The iterator does not restart on its own (that would yield the first steps again).
    expect(got).toEqual([1, 2]);

    expired.clear();
    expect(numbers(await collect(client.sessions.iterSteps('s-1')))).toEqual([1, 2, 3, 4]);
    expect(calls.map(url => url.searchParams.get('cursor'))).toEqual([null, CURSOR_2, null, CURSOR_2, CURSOR_3]);
  });

  // Session object

  it('session object iterates and pages, also after stop()', async () => {
    const session = client.Session();
    await expect(session.steps()).rejects.toThrow('Session not started');
    await session.start();
    expect(numbers(await collect(session.iterSteps({ limit: 2 })))).toEqual([1, 2, 3, 4]);
    expect(queries()).toEqual([{ limit: '2' }, { cursor: CURSOR_2, limit: '2' }, { cursor: CURSOR_3, limit: '2' }]);

    await session.stop();
    calls = [];
    expect(await session.steps({ cursor: CURSOR_3 })).toEqual(PAGES.get(CURSOR_3));
    expect(queries()).toEqual([{ cursor: CURSOR_3 }]);
  });

  it('session object raises the 400 and restarts from the first page', async () => {
    const session = client.Session();
    await session.start();
    expired.add(CURSOR_2);
    const got: unknown[] = [];
    const error = await (async () => {
      for await (const step of session.iterSteps()) got.push(step.n);
    })().catch((e: unknown) => e);
    expect((error as NotteAPIError).statusCode).toBe(400);
    expect(got).toEqual([1, 2]);
    expired.clear();
    expect(numbers(await collect(session.iterSteps()))).toEqual([1, 2, 3, 4]);
  });
});
