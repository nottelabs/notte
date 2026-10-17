import assert from 'node:assert/strict';
import { mock, test } from 'node:test';
import { NotteClient, Session, sessionStatus } from 'notte-sdk';
import { chromium } from 'playwright-core';
import { run } from '../src/index.ts';

const live = process.env.NOTTE_FX_LIVE === '1';
const credential = 'notte-offline-test-credential'; // pragma: allowlist secret
if (!live) process.env.NOTTE_API_KEY = credential;
const provider = { name: 'fixture', baseUrl: 'http://localhost:9/v1', models: { fixture: { contextWindow: 32_000, maxOutputTokens: 1024, supportsToolUse: true } } };

async function closed(id: string) {
  const client = new NotteClient();
  const signal = AbortSignal.timeout(15_000);
  while (!signal.aborted) {
    const response = await sessionStatus({ client: client.getClient(), path: { session_id: id }, throwOnError: true, signal });
    if (response.data.status === 'closed') return;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error('The owned browser session did not close');
}

async function owned(operation: () => Promise<unknown>, browserExpected = true) {
  if (live) {
    assert.ok(process.env.NOTTE_API_KEY);
    assert.ok(process.env.NOTTE_API_URL, 'Choose the browser API explicitly');
    const ids: string[] = [], stop = Session.prototype.stop;
    const interception = mock.method(Session.prototype, 'stop', async function (this: Session, ...args: Parameters<Session['stop']>) {
      ids.push(this.getId()!);
      return await stop.apply(this, args);
    });
    try { await operation(); }
    finally {
      interception.mock.restore();
      assert.equal(ids.length, 1, 'Exactly one owned browser must be stopped');
      await closed(ids[0]);
    }
    return;
  }
  let stopped = false, disconnected = false;
  const session = { getId: () => 'owned', cdpUrl: async () => `wss://example.invalid?api_key=${credential}` };
  const page = {
    goto: async (url: string) => { if (url === 'http://127.0.0.1:1') throw new Error(credential); },
    title: async () => 'Example Domain',
  };
  const browser = { contexts: () => [{ newPage: async () => page }], close: async () => { disconnected = true; } };
  const sessionMock = mock.method(NotteClient.prototype, 'Session', (() => ({
    use: async (execute: (value: typeof session) => Promise<unknown>) => {
      try { return await execute(session); } finally { stopped = true; }
    },
  })) as never);
  const connectionMock = mock.method(chromium, 'connectOverCDP', (async () => browser) as never);
  try { await operation(); }
  finally {
    sessionMock.mock.restore();
    connectionMock.mock.restore();
    assert.ok(stopped, 'The owned browser must be stopped');
    assert.equal(disconnected, browserExpected, 'The CDP connection must close');
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
    if (unauthorized) return Response.json({ error: { message: 'Injected unauthorized', type: 'authentication_error' } }, { status: 401 });
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
  await owned(() => assert.rejects(() => run('Read the page title', fixture.options), /^Error: fx browser task failed \(session [a-z0-9-]+\)$/), false);
  assert.equal(fixture.requests.length, 1);
});
