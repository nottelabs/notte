/** Remote `fetch()`: the request runs in the page via `evaluateJs` and comes back as a `PageFetchResponse`. Mirrors `tests/sdk/test_fetch_helper.py`. */
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { Session } from '@/session';
import { buildFetchScript, PageFetchHTTPError, PageFetchResponse, responseFromEvaluated } from '@/page-fetch';
import { FetchResponseDecodeError, InvalidRequestError } from '@/errors';
import { pageExecute, sessionStart } from '@/lib/client/sdk.gen';
import type { ApiExecutionResponse } from '@/lib/client/types.gen';
import { executionResult, mockNotteClient, overTheWire, sessionResponse } from './helpers/session-mocks';

vi.mock('@/lib/client/sdk.gen', () => ({
  sessionStart: vi.fn(),
  sessionStop: vi.fn(),
  pageExecute: vi.fn(),
}));

function envelope(options: {
  status?: number;
  text?: string;
  url?: string;
  contentType?: string;
  body?: Uint8Array;
} = {}): string {
  const { status = 200, text = '{"ok": true}', url = 'https://example.com/api', contentType = 'application/json', body } = options;
  const payload = body ?? new TextEncoder().encode(text);
  return JSON.stringify({
    status,
    url,
    headers: { 'content-type': contentType },
    body_b64: Buffer.from(payload).toString('base64'),
  });
}

function evalResult(markdown: string): ApiExecutionResponse {
  return executionResult({ action: { type: 'evaluate_js', code: 'fetch' }, data: { markdown } });
}

async function remoteSession(result: ApiExecutionResponse): Promise<Session> {
  vi.mocked(sessionStart).mockResolvedValue({ data: sessionResponse() } as never);
  vi.mocked(pageExecute).mockResolvedValue({ data: result } as never);
  const session = new Session(mockNotteClient());
  await session.start();
  return session;
}

// --- the script -----------------------------------------------------------------

describe('buildFetchScript', () => {
  it('defaults to a credentialed GET with no body', () => {
    const script = buildFetchScript('/api');

    expect(script.startsWith('(async () => {')).toBe(true);
    expect(script).toContain('"method":"GET"');
    expect(script).toContain('"credentials":"include"');
    expect(script).toContain('"redirect":"follow"');
    expect(script).toContain('new URL("/api", location.href)');
    expect(script).toContain('fetch(target.toString(), init)');
    expect(script).not.toContain('"body"');
    expect(script).not.toContain('AbortController');
    expect(script).toContain('body_b64: btoa(binary)');
  });

  it('appends params to the query string', () => {
    expect(buildFetchScript('/api', { params: { page: 2, q: 'a b' } })).toContain('new URL("/api?page=2&q=a+b", location.href)');
    expect(buildFetchScript('/api?x=1', { params: { page: 2 } })).toContain('new URL("/api?x=1&page=2", location.href)');
    // before the fragment, which the browser strips before sending
    expect(buildFetchScript('/items#results', { params: { page: 2 } })).toContain('new URL("/items?page=2#results", location.href)');
    expect(buildFetchScript('https://a.test/p?x=1#f', { params: { page: 2 } })).toContain('new URL("https://a.test/p?x=1&page=2#f", location.href)');
    // array values repeat the key, like `doseq=True`
    expect(buildFetchScript('/api', { params: { tag: ['a', 'b'] } })).toContain('new URL("/api?tag=a&tag=b", location.href)');
    // empty params leave the url alone
    expect(buildFetchScript('/api', { params: {} })).toContain('new URL("/api", location.href)');
  });

  it('serialises a JSON body and sets the content type', () => {
    const script = buildFetchScript('/graphql', { method: 'post', json: { query: '{ me }' } });

    expect(script).toContain('"method":"POST"');
    expect(script).toContain('"Content-Type":"application/json"');
    expect(script).toContain(JSON.stringify(JSON.stringify({ query: '{ me }' })));
  });

  it('keeps a caller content type', () => {
    const script = buildFetchScript('/x', {
      method: 'POST',
      json: {},
      headers: { 'content-type': 'application/graphql-response+json' },
    });

    expect(script.split('ontent-').length - 1).toBe(1);
    expect(script).toContain('application/graphql-response+json');
  });

  it('form-encodes an object and passes a string through', () => {
    const form = buildFetchScript('/login', { method: 'POST', data: { user: 'a b', pw: 'c' } });
    expect(form).toContain('"body":"user=a+b&pw=c"');
    expect(form).toContain('"Content-Type":"application/x-www-form-urlencoded"');

    const raw = buildFetchScript('/raw', { method: 'PUT', data: '<xml/>' });
    expect(raw).toContain('"body":"<xml/>"');
    expect(raw).not.toContain('Content-Type');
  });

  it('rejects json and data together', () => {
    expect(() => buildFetchScript('/x', { json: {}, data: 'y' })).toThrow(InvalidRequestError);
    expect(() => buildFetchScript('/x', { json: {}, data: 'y' })).toThrow('pass either json or data, not both');
  });

  it('rejects a body on GET and HEAD', () => {
    expect(() => buildFetchScript('/x', { json: { a: 1 } })).toThrow('GET requests cannot have a body');
    expect(() => buildFetchScript('/x', { method: 'head', data: 'y' })).toThrow('HEAD requests cannot have a body');
  });

  it('aborts after the timeout', () => {
    const script = buildFetchScript('/slow', { timeoutMs: 2500 });

    expect(script).toContain('controller.abort(), 2500');
    expect(script).toContain('init.signal = controller.signal');
    expect(() => buildFetchScript('/slow', { timeoutMs: 0 })).toThrow('positive');
    expect(() => buildFetchScript('/slow', { timeoutMs: -1 })).toThrow('positive');
  });
});

// --- the response ----------------------------------------------------------------

describe('session.fetch', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  it('returns a PageFetchResponse', async () => {
    const session = await remoteSession(overTheWire(evalResult(envelope())));

    const response = await session.fetch('/api');

    expect(response).toBeInstanceOf(PageFetchResponse);
    expect(response.status).toBe(200);
    expect(response.ok).toBe(true);
    expect(response.statusText).toBe('OK');
    expect(await response.json()).toEqual({ ok: true });
    expect(await response.text()).toBe('{"ok": true}');
    expect(new TextDecoder().decode(response.bytes())).toBe('{"ok": true}');
    expect(new TextDecoder().decode(await response.arrayBuffer())).toBe('{"ok": true}');
    // browsers lowercase header names; `Headers` keeps the lookup case-insensitive
    expect(response.headers.get('Content-Type')).toBe('application/json');
    expect(response.url).toBe('https://example.com/api');
    expect(response.raiseForStatus()).toBe(response);
    // the script built from the arguments is what ran in the page
    expect(pageExecute).toHaveBeenCalledWith(
      expect.objectContaining({ body: { type: 'evaluate_js', code: buildFetchScript('/api') } }),
    );
  });

  it('forwards the request options to the script', async () => {
    const session = await remoteSession(overTheWire(evalResult(envelope())));
    await session.fetch('/items', { method: 'post', json: { a: 1 }, params: { page: 2 }, timeoutMs: 1000 });
    expect(pageExecute).toHaveBeenCalledWith(
      expect.objectContaining({
        body: { type: 'evaluate_js', code: buildFetchScript('/items', { method: 'post', json: { a: 1 }, params: { page: 2 }, timeoutMs: 1000 }) },
      }),
    );
  });

  it('returns http errors and raises only when asked', async () => {
    const session = await remoteSession(overTheWire(evalResult(envelope({ status: 403, text: 'denied' }))));

    const response = await session.fetch('/api');

    expect(response.status).toBe(403);
    expect(response.ok).toBe(false);
    expect(await response.text()).toBe('denied');
    let raised: unknown;
    try {
      response.raiseForStatus();
    } catch (error) {
      raised = error;
    }
    expect(raised).toBeInstanceOf(PageFetchHTTPError);
    expect((raised as Error).message).toContain('403 Client Error: Forbidden');
    expect((raised as PageFetchHTTPError).response).toBe(response);
  });

  it('preserves binary bodies byte for byte', async () => {
    const payload = new Uint8Array([0x63, 0x61, 0x66, 0xe9, 0x00, 0xff]);
    const session = await remoteSession(
      overTheWire(evalResult(envelope({ contentType: 'application/octet-stream', body: payload }))),
    );

    const response = await session.fetch('/blob');

    expect([...response.bytes()]).toEqual([...payload]);
    // undeclared charset and not valid utf-8: no encoding is forced
    expect(response.encoding).toBeUndefined();
  });

  it('decodes text with the declared charset', async () => {
    const payload = new Uint8Array([0x63, 0x61, 0x66, 0xe9]); // "café" in latin-1
    const session = await remoteSession(
      overTheWire(evalResult(envelope({ contentType: 'text/html; charset=ISO-8859-1', body: payload }))),
    );

    const response = await session.fetch('/page');

    expect(response.encoding).toBe('ISO-8859-1');
    expect(await response.text()).toBe('café');
  });

  it('rejects an unreadable envelope', async () => {
    const session = await remoteSession(overTheWire(evalResult('not json')));
    await expect(session.fetch('/api')).rejects.toBeInstanceOf(FetchResponseDecodeError);
  });
});

describe('responseFromEvaluated', () => {
  it('rejects envelopes that are not objects', () => {
    expect(() => responseFromEvaluated('[1]')).toThrow('envelope is not an object');
    expect(() => responseFromEvaluated('null')).toThrow('envelope is not an object');
  });

  it('rejects envelopes with a missing or invalid status', () => {
    expect(() => responseFromEvaluated('{}')).toThrow(FetchResponseDecodeError);
    expect(() => responseFromEvaluated('{"status": "abc"}')).toThrow('invalid status');
  });

  it('rejects invalid base64 bodies', () => {
    expect(() => responseFromEvaluated('{"status": 200, "body_b64": "%%%"}')).toThrow('not valid base64');
  });

  it('defaults headers, url and body', () => {
    const response = responseFromEvaluated('{"status": 204}');
    expect(response.status).toBe(204);
    expect(response.statusText).toBe('No Content');
    expect(response.url).toBe('');
    expect(response.bytes().length).toBe(0);
    expect(response.encoding).toBe('utf-8');
  });
});

describe('buildFetchScript plaintext guard (CWE-319)', () => {
  it('resolves the url against the page and refuses http targets by default', () => {
    const script = buildFetchScript('/api/items');
    expect(script).toContain('new URL("/api/items", location.href)');
    expect(script).toContain("target.protocol !== 'https:' && !allowInsecure");
    expect(script).toContain('const allowInsecure = false;');
    expect(script).toContain("new URL(response.url).protocol !== 'https:'");
  });

  it('allowInsecure lets http requests and redirects through', () => {
    const script = buildFetchScript('http://intranet.local/status', { allowInsecure: true });
    expect(script).toContain('const allowInsecure = true;');
  });
});
