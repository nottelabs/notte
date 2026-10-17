import assert from 'node:assert/strict';
import { appendFileSync } from 'node:fs';
import { mock, test } from 'node:test';
import { NotteClient, sessionStatus } from 'notte-sdk';
import { chromium } from 'playwright-core';
import { run } from '../src/index.ts';

const live = process.env.NOTTE_FX_LIVE === '1';
const credential = 'notte-offline-test-credential'; // pragma: allowlist secret
if (!live) process.env.NOTTE_API_KEY = credential;
const provider = { name: 'fixture', baseUrl: 'http://localhost:9/v1', models: { fixture: { contextWindow: 32_000, maxOutputTokens: 1024, supportsToolUse: true } } };

function journal(event: string, session_id: string) {
  if (process.env.NOTTE_FX_OWNERSHIP_JOURNAL) {
    try { appendFileSync(process.env.NOTTE_FX_OWNERSHIP_JOURNAL, JSON.stringify({ event, session_id }) + '\n', { mode: 0o600, flush: true }); }
    catch { console.warn('Ownership journal unavailable'); }
  }
}

async function closed(id: string) {
  const client = new NotteClient();
  const signal = AbortSignal.timeout(15_000);
  while (!signal.aborted) {
    const response = await sessionStatus({ client: client.getClient(), path: { session_id: id }, throwOnError: true, signal });
    if (response.data.status === 'closed') { journal('closed', id); return; }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error('The owned browser session did not close');
}

async function owned<T>(operation: () => Promise<T>, browserExpected = true, pending?: AbortController, fault?: 'reject' | 'stall'): Promise<T> {
  const originalTimeout = AbortSignal.timeout.bind(AbortSignal);
  const deadline = pending ? mock.method(AbortSignal, 'timeout', (milliseconds: number) => milliseconds === 90_000 ? pending.signal : originalTimeout(milliseconds)) : undefined;
  let closes = 0;
  if (live) {
    assert.ok(process.env.NOTTE_API_KEY);
    assert.ok(process.env.NOTTE_API_URL, 'Choose the browser API explicitly');
    const ids: string[] = [];
    let navigationStarted = false, closeStarted = 0, stopAfterClose = 0;
    const originalFetch = globalThis.fetch;
    const interception = mock.method(globalThis, 'fetch', async (...args: Parameters<typeof fetch>) => {
      const [input, options] = args;
      const url = new URL(input instanceof Request ? input.url : String(input));
      if (pending && /\/sessions\/[^/]+\/stop$/.test(url.pathname)) stopAfterClose = closeStarted ? performance.now() - closeStarted : -1;
      const response = await originalFetch(input, options);
      if (url.pathname.endsWith('/sessions/start') && response.ok) {
        const body = await response.clone().json();
        if (typeof body.session_id === 'string') {
          ids.push(body.session_id);
          journal('allocated', body.session_id);
        }
      }
      return response;
    });
    const connect = chromium.connectOverCDP.bind(chromium);
    let cleanup: (() => Promise<void>) | undefined;
    const connection = pending || fault ? mock.method(chromium, 'connectOverCDP', async (...args: Parameters<typeof chromium.connectOverCDP>) => {
      const browser = await connect(...args), nativeClose = browser.close.bind(browser);
      if (pending) {
        const context = browser.contexts()[0], newPage = context.newPage.bind(context);
        context.newPage = async (...options) => {
          const page = await newPage(...options);
          await page.route('https://fx-owned.invalid/**', () => {
            navigationStarted = true;
            pending.abort();
          });
          return page;
        };
      }
      browser.close = async () => {
        closes++;
        closeStarted = performance.now();
        if (pending && fault === 'stall') await new Promise<void>(() => {});
        await nativeClose();
        if (fault === 'stall') await new Promise<void>(() => {});
        if (fault === 'reject') throw new Error('PRIVATE_CLOSE_FIXTURE');
      };
      cleanup = async () => {
        let timer: ReturnType<typeof setTimeout> | undefined;
        try { await Promise.race([nativeClose(), new Promise<void>(resolve => { timer = setTimeout(resolve, 5_000); })]); }
        finally { clearTimeout(timer); }
      };
      return browser;
    }) : undefined;
    try { return await operation(); }
    finally {
      interception.mock.restore();
      connection?.mock.restore();
      deadline?.mock.restore();
      try {
        for (const id of ids) {
          try { await closed(id); }
          catch (error) {
            const response = await originalFetch(`${process.env.NOTTE_API_URL}/sessions/${id}/stop`, {
              method: 'DELETE', headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` }, signal: AbortSignal.timeout(15_000),
            });
            assert.ok(response.ok, 'Owned fallback stop failed');
            await closed(id);
            throw error;
          }
        }
      } finally { if (cleanup) await cleanup(); }
      assert.equal(ids.length, 1, 'Exactly one owned browser must be allocated');
      if (pending || fault) assert.equal(closes, 1, 'Only one native disconnect should run');
      if (pending) {
        assert.ok(navigationStarted, 'A real browser request must be pending before cancellation');
        assert.ok(stopAfterClose >= (fault === 'stall' ? 4_900 : 0), 'The owned tool cleanup must finish before API stop');
      }
    }
  }
  let stopped = false, disconnected = false;
  const session = { getId: () => 'owned', cdpUrl: async () => `wss://example.invalid?api_key=${credential}` };
  const page = {
    goto: async (url: string) => {
      if (url === 'http://127.0.0.1:1') throw new Error(credential);
      if (pending) {
        queueMicrotask(() => pending.abort());
        await new Promise<void>(() => {});
      }
    },
    title: async () => 'Example Domain',
  };
  const browser = { contexts: () => [{ newPage: async () => page }], close: async () => {
    closes++;
    disconnected = true;
    if (fault === 'stall') await new Promise<void>(() => {});
    if (fault === 'reject') throw new Error('PRIVATE_CLOSE_FIXTURE');
  } };
  const sessionMock = mock.method(NotteClient.prototype, 'Session', (() => ({
    use: async (execute: (value: typeof session) => Promise<unknown>) => {
      try { return await execute(session); } finally { stopped = true; }
    },
  })) as never);
  const connectionMock = mock.method(chromium, 'connectOverCDP', (async () => browser) as never);
  try { return await operation(); }
  finally {
    sessionMock.mock.restore();
    connectionMock.mock.restore();
    deadline?.mock.restore();
    assert.ok(stopped, 'The owned browser must be stopped');
    assert.equal(disconnected, browserExpected, 'The CDP connection must close');
    assert.equal(closes, browserExpected ? 1 : 0, 'The tool must retain one disconnect operation');
  }
}

function scriptedProvider(url: string, unauthorized = false) {
  const requests: Record<string, unknown>[] = [];
  const fetch: NonNullable<Parameters<typeof run>[1]>['fetch'] = async (input, init) => {
    assert.equal(String(input), 'http://localhost:9/v1/chat/completions');
    const body = JSON.parse(String(init?.body));
    requests.push(body);
    assert.equal(JSON.stringify(body).includes(process.env.NOTTE_API_KEY!), false, 'Model request exposed the Notte key');
    assert.equal(JSON.stringify(body).includes('wss://'), false, 'Model request exposed a CDP credential');
    if (unauthorized) return Response.json({ error: { message: 'PRIVATE_PROVIDER_FIXTURE', type: 'authentication_error' } }, { status: 401 });
    const delta = requests.length === 1
      ? { role: 'assistant', tool_calls: [{ index: 0, id: 'read1', type: 'function', function: { name: 'read_page', arguments: JSON.stringify({ url }) } }] }
      : { role: 'assistant', content: url.includes('127.0.0.1') ? 'Browser unavailable' : 'Example Domain' };
    const chunks = [
      { choices: [{ index: 0, delta, finish_reason: null }] },
      { choices: [{ index: 0, delta: {}, finish_reason: requests.length === 1 ? 'tool_calls' : 'stop' }] },
    ];
    return new Response(chunks.map(chunk => `data: ${JSON.stringify(chunk)}\n\n`).join('') + 'data: [DONE]\n\n', { headers: { 'content-type': 'text/event-stream' } });
  };
  return { requests, options: { provider, model: 'fixture', fetch } };
}

test('The native fx engine calls the browser tool and sees its real title', { timeout: 120_000 }, async () => {
  const fixture = scriptedProvider('https://example.com');
  await owned(async () => {
    const result = await run('Read the page title', fixture.options);
    assert.equal(result.answer, 'Example Domain');
    assert.ok(result.session_id);
  });
  assert.equal(fixture.requests.length, 2);
  const first = fixture.requests[0] as { tools: { function: { name: string; parameters: object } }[] };
  assert.deepEqual(first.tools.map(tool => tool.function.name), ['read_page']);
  assert.equal(JSON.stringify(first.tools).includes('session_id'), false);
  assert.ok(JSON.stringify(fixture.requests[1]).includes('Example Domain'));
});

test('Navigation errors reach fx safely and the owned browser closes', { timeout: 120_000 }, async () => {
  const fixture = scriptedProvider('http://127.0.0.1:1');
  await owned(async () => {
    const result = await run('Read the page title', fixture.options);
    assert.equal(result.answer, 'Browser unavailable');
  });
  assert.equal(fixture.requests.length, 2);
  assert.ok(JSON.stringify(fixture.requests[1]).includes('Notte page navigation failed'));
});

test('Native provider HTTP 401 fails once and closes the owned browser', { timeout: 120_000 }, async () => {
  const fixture = scriptedProvider('https://example.com', true);
  let failure: unknown;
  await owned(async () => { try { await run('Read the page title', fixture.options); } catch (error) { failure = error; } }, false);
  assert.ok(failure instanceof Error, 'The provider must reject');
  assert.ok(/^fx browser task failed \(session [a-z0-9-]+\)$/.test(failure.message), 'The provider failure must remain safe');
  assert.ok(failure.cause === undefined, 'The safe error must not retain a private cause');
  assert.ok(!failure.message.includes('PRIVATE_PROVIDER_FIXTURE'), 'Private provider diagnostics leaked');
  assert.equal(fixture.requests.length, 1);
});

for (const fault of ['reject', 'stall'] as const) {
  test(`The native engine keeps navigation errors private when disconnect ${fault}s`, { timeout: 120_000 }, async () => {
    const fixture = scriptedProvider('http://127.0.0.1:1');
    await owned(async () => {
      const result = await run('Read the page title', fixture.options);
      assert.equal(result.answer, 'Browser unavailable');
    }, true, undefined, fault);
    const body = JSON.stringify(fixture.requests[1]);
    assert.ok(body.includes('Notte page navigation failed'), 'The engine must receive the safe tool failure');
    assert.ok(!body.includes('PRIVATE_CLOSE_FIXTURE'), 'Private close diagnostics entered the provider request');
  });
}

for (const fault of [undefined, 'stall'] as const) {
  test(`Native cancellation joins the browser tool before owner stop${fault ? ' despite stalled disconnect' : ''}`, { timeout: live ? 120_000 : 8_000 }, async () => {
    const controller = new AbortController();
    const fixture = scriptedProvider('https://fx-owned.invalid/pending');
    const started = performance.now();
    let failure: unknown;
    await owned(async () => { try { await run('Read the page title', fixture.options); } catch (error) { failure = error; } }, true, controller, fault);
    assert.ok(controller.signal.aborted, 'The native turn deadline must abort');
    assert.ok(failure instanceof Error, 'The cancelled turn must reject');
    assert.ok(/^fx browser task failed \(session [a-z0-9-]+\)$/.test(failure.message), 'Cancellation must remain safe');
    assert.ok(failure.cause === undefined, 'Cancellation must not retain a private cause');
    if (!live && fault) assert.ok(performance.now() - started >= 4_900, 'Owner cleanup must join the bounded disconnect');
    assert.equal(fixture.requests.length, 1, 'The cancelled native turn must not make another model request');
  });
}
