import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { test } from 'node:test';
import { DynamicStructuredTool } from '@langchain/core/tools';
import { MCPAdapter } from '@langchain/mcp-adapters';
import { NotteClient, sessionStatus } from 'notte-sdk';
import { browserTools, run } from '../src/index.ts';

const live = process.env.NOTTE_DEEPAGENTS_LIVE === '1';

test('Model arguments cannot change the owned browser or expose session tools', async () => {
  const names = ['notte_browser_action', 'notte_browser_observe', 'notte_browser_scrape', 'notte_session_start'];
  const remote = names.map(name => new DynamicStructuredTool({
    name, description: name,
    schema: { type: 'object' as const, properties: { browser_id: { type: 'string' as const } }, required: ['browser_id'] },
    func: async args => (args as { browser_id: string }).browser_id,
  }));
  const tools = browserTools(remote, 'owned-session');
  assert.deepEqual(tools.map(tool => tool.name), names.slice(0, 3));
  for (const tool of tools) assert.equal(await tool.invoke({ browser_id: 'another-session' }), 'owned-session');
});

async function closed(id: string) {
  const client = new NotteClient();
  const signal = AbortSignal.timeout(15_000);
  while (!signal.aborted) {
    const response = await sessionStatus({ client: client.getClient(), path: { session_id: id }, throwOnError: true, signal });
    if (response.data.status === 'closed') return response.data;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error('The owned browser session did not close');
}

async function owned<T>(operation: () => Promise<T>) {
  assert.ok(process.env.NOTTE_API_URL, 'Choose the browser API explicitly');
  const original = globalThis.fetch, ids: string[] = [];
  globalThis.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const response = await original(input, init);
    if (new URL(url).pathname === '/sessions/start' && response.ok) ids.push((await response.clone().json()).session_id);
    return response;
  };
  let result: T;
  try { result = await operation(); }
  finally {
    try {
      for (const id of ids) await closed(id);
      assert.equal(ids.length, 1, 'The example must own exactly one browser session');
    } finally { globalThis.fetch = original; }
  }
  return { result, status: await closed(ids[0]), ids };
}

test('Deep Agents navigates the owned browser and closes it', {
  skip: !live || process.env.NOTTE_DEEPAGENTS_MODEL_LIVE !== '1', timeout: 180_000,
}, async () => {
  const { result, status, ids } = await owned(() => run('Visit https://example.com and report its page title.'));
  assert.match(result.answer, /Example Domain/);
  assert.deepEqual(ids, [result.session_id]);
  assert.ok(status.steps?.some(step => {
    const value = step.value as { success?: boolean; action?: { type?: string; url?: string } } | undefined;
    return step.type === 'execution_result' && value?.success === true
      && value.action?.type === 'goto' && value.action.url?.replace(/\/$/, '') === 'https://example.com';
  }), 'The persisted browser history must prove successful navigation');
});

test('A real framework provider 401 survives MCP close failure and closes the browser', { skip: !live, timeout: 120_000 }, async t => {
  let closes = 0;
  const originalClose = MCPAdapter.prototype.close;
  t.mock.method(MCPAdapter.prototype, 'close', async function(this: MCPAdapter) {
    await originalClose.call(this);
    closes++;
    throw new Error('Cleanup transport error https://private.invalid/credential');
  });
  let requests = 0;
  let tools: string[] = [];
  const server = createServer((request, response) => {
    let body = '';
    request.on('data', chunk => { body += chunk; });
    request.on('end', () => {
      requests++;
      tools = JSON.parse(body).tools.map((tool: { name: string }) => tool.name);
      response.writeHead(401, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ type: 'error', error: { type: 'authentication_error', message: 'Injected authentication failure' } }));
    });
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const key = process.env.ANTHROPIC_API_KEY, base = process.env.ANTHROPIC_BASE_URL;
  try {
    const address = server.address();
    assert.ok(address && typeof address !== 'string');
    process.env.ANTHROPIC_BASE_URL = `http://127.0.0.1:${address.port}`;
    process.env.ANTHROPIC_API_KEY = 'not-a-real-key'; // pragma: allowlist secret
    await assert.rejects(owned(() => run('Read the page title')),
      /^Error: Deep Agents failed during agent execution: AuthenticationError HTTP 401 \(session [0-9a-f-]{36}\)$/);
    assert.equal(requests, 1, 'The actual framework must reach the injected provider');
    assert.equal(closes, 1, 'The adapter close must inject a genuine cleanup failure');
    assert.equal(tools.some(name => ['glob', 'grep', 'execute'].includes(name)), false);
    assert.ok(tools.includes('read_file'));
  } finally {
    if (key === undefined) delete process.env.ANTHROPIC_API_KEY; else process.env.ANTHROPIC_API_KEY = key;
    if (base === undefined) delete process.env.ANTHROPIC_BASE_URL; else process.env.ANTHROPIC_BASE_URL = base;
    server.closeAllConnections();
    await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  }
});
