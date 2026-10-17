import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { AddressInfo } from 'node:net';
import { test } from 'node:test';
import { setTimeout as sleep } from 'node:timers/promises';
import { loadAction, runDemo } from '../demo.ts';

const config = { clientId: 'fixture-client', clientSecret: 'fixture-secret', projectId: 'proj_fixture', externalUserId: 'user-fixture' }; // pragma: allowlist secret

async function closed(id: string) {
  const api = (process.env.NOTTE_API_URL || 'https://api.notte.cc').replace(/\/$/, '');
  const deadline = Date.now() + 15_000;
  while (true) {
    const response = await fetch(`${api}/sessions/${id}`, { headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY!}` }, signal: AbortSignal.timeout(15_000) });
    assert.equal(response.status, 200, 'Independent lookup failed');
    const row = await response.json() as { status: string; steps: { type?: string; value?: { action?: { url?: string }; success?: boolean } }[] };
    if (row.status === 'closed') return row;
    assert.ok(Date.now() < deadline, `Owned browser ${id} remains active`);
    await sleep(500);
  }
}

for (const mode of ['success', 'action', 'action_error', 'unoffered', 'pagination', 'cursor_cycle', 'oauth401', 'mcp401', 'navigation', 'cancel']) {
  test(`native MCP ${mode} and owned browser cleanup`, { timeout: 100_000 }, async (t) => {
    const warnings: string[] = [];
    const warn = console.warn;
    console.warn = (...args: unknown[]) => { warnings.push(args.map(String).join(' ')); warn(...args); };
    t.after(() => { console.warn = warn; });
    const requests: { path: string; headers: Record<string, unknown>; body: any }[] = [];
    const controller = new AbortController();
    const server = createServer(async (req, res) => {
      let raw = '';
      for await (const part of req) raw += part.toString();
      const body = raw ? JSON.parse(raw) : {};
      requests.push({ path: req.url!, headers: req.headers, body });
      const reply = (value: unknown, status = 200) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(value)); };
      if (req.url === '/v1/oauth/token') return reply(mode === 'oauth401' ? { error: 'private fixture-secret detail' } : { access_token: 'fixture-access-token', token_type: 'Bearer', expires_in: 3600 }, mode === 'oauth401' ? 401 : 200);
      if (req.url !== '/v3') return reply({}, 404);
      if (mode === 'mcp401') return reply({ error: 'private fixture-access-token detail' }, 401);
      if (req.method === 'GET') return reply({}, 405);
      if (req.method === 'DELETE') return reply({});
      if (body.id === undefined) { res.writeHead(202); return res.end(); }
      if (body.method === 'tools/list' && mode === 'cancel') {
        controller.abort();
        return;
      }
      const paginated = ['pagination', 'cursor_cycle'].includes(mode);
      const cursor = body.params?.cursor;
      const result = body.method === 'initialize'
        ? { protocolVersion: body.params.protocolVersion, capabilities: { tools: {} }, serverInfo: { name: 'local-pipedream-fixture', version: '1' } }
        : body.method === 'tools/call' ? { content: [{ type: 'text', text: 'private fixture-output detail' }], isError: mode === 'action_error' }
        : { tools: [{ name: paginated && !cursor ? 'fixture_first_page' : 'fixture_catalog_read', description: 'Synthetic test tool, not a vendor action', inputSchema: { type: 'object', properties: {} }, annotations: { readOnlyHint: true } }], ...(paginated && (!cursor || mode === 'cursor_cycle') ? { nextCursor: 'fixture-next' } : {}) };
      reply({ jsonrpc: '2.0', id: body.id, result });
    });
    await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
    t.after(() => { server.closeAllConnections(); return new Promise<void>((resolve) => server.close(() => resolve())); });
    const port = (server.address() as AddressInfo).port;
    const providerFetch: typeof fetch = (input, init) => {
      const url = new URL(String(input));
      assert.ok(['https://api.pipedream.com', 'https://remote.mcp.pipedream.net'].includes(url.origin), 'Unexpected provider host');
      assert.equal(init?.redirect, 'error');
      const headers = new Headers(init?.headers);
      assert.ok(headers.get('authorization') !== `Bearer ${process.env.NOTTE_API_KEY!}`, 'Notte credentials must never reach Pipedream');
      return fetch(`http://127.0.0.1:${port}${url.pathname}`, { ...init, redirect: 'error' });
    };
    let id: string;
    const run = runDemo(config, { approvedAction: ['action', 'action_error', 'unoffered', 'pagination', 'cursor_cycle'].includes(mode) ? { name: mode === 'unoffered' ? 'fixture_not_offered' : 'fixture_catalog_read', arguments: { private: 'fixture-private-argument' } } : undefined, providerFetch, signal: controller.signal, pageUrl: mode === 'navigation' ? 'https://notte-pipedream-missing.invalid' : 'https://example.com' });
    if (['success', 'action', 'pagination'].includes(mode)) {
      const result = await run;
      id = result.session_id;
      assert.match(JSON.stringify(result.page), /Example Domain/);
      assert.deepEqual(result.tool_names, mode === 'pagination' ? ['fixture_first_page', 'fixture_catalog_read'] : ['fixture_catalog_read']);
      assert.equal(result.tool_call_completed, ['action', 'pagination'].includes(mode));
      assert.doesNotMatch(JSON.stringify(result), /fixture-private-argument|fixture-output/);
    } else {
      try { await run; assert.fail('Expected the real failure'); }
      catch (error) {
        assert.ok(error instanceof Error);
        assert.doesNotMatch(error.message, /fixture-secret|fixture-access-token|fixture-private-argument|fixture-output/);
        id = error.message.match(/session ([a-f0-9-]{36})/)![1];
      }
    }
    const row = await closed(id);
    assert.doesNotMatch(warnings.join('\n'), /fixture-secret|fixture-access-token|fixture-private-argument|fixture-output/, 'Provider response details must stay out of SDK cleanup logs');
    if (mode !== 'navigation') assert.ok(row.steps.some((step) => step.type === 'execution_result' && step.value?.action?.url === 'https://example.com' && step.value.success === true), 'Persisted steps must prove real browser navigation');
    if (mode === 'navigation') assert.deepEqual(requests, []);
    else {
      assert.deepEqual(requests[0].body, { grant_type: 'client_credentials', client_id: config.clientId, client_secret: config.clientSecret });
      for (const request of requests.filter((entry) => entry.path === '/v3')) {
        assert.equal(request.headers.authorization, 'Bearer fixture-access-token');
        assert.equal(request.headers['x-pd-project-id'], config.projectId);
        assert.equal(request.headers['x-pd-external-user-id'], config.externalUserId);
        assert.equal(request.headers['x-pd-environment'], 'development');
        assert.equal(request.headers['x-pd-app-slug'], 'github');

      }
    }
    const calls = requests.filter((entry) => entry.body.method === 'tools/call');
    assert.equal(calls.length, ['action', 'action_error', 'pagination'].includes(mode) ? 1 : 0);
    if (['pagination', 'cursor_cycle'].includes(mode)) {
      const lists = requests.filter((entry) => entry.body.method === 'tools/list');
      assert.equal(lists.length, 2);
      assert.equal(lists[1].body.params.cursor, 'fixture-next');
    }
    if (calls.length) assert.deepEqual(calls[0].body.params, { name: 'fixture_catalog_read', arguments: { private: 'fixture-private-argument' } });
    console.log(`${mode}: owned browser ${id} independently closed`);
  });
}


test('private action file validation keeps its contents out of errors', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'notte-approved-action-'));
  try {
    const path = join(directory, 'action.json');
    await writeFile(path, JSON.stringify({ name: 'fixture-private-argument', arguments: [] }), { mode: 0o600 });
    await assert.rejects(loadAction(path), (error: unknown) => {
      assert.ok(error instanceof Error);
      assert.equal(error.message, 'Action file must contain a tool name and arguments object');
      return true;
    });
    await writeFile(path, JSON.stringify({ name: 'fixture_catalog_read', arguments: {} }));
    assert.deepEqual(await loadAction(path), { name: 'fixture_catalog_read', arguments: {} });
    assert.equal(await loadAction(undefined), undefined);
  } finally { await rm(directory, { recursive: true, force: true }); }
});


for (const phase of ['claim', 'mcp']) {
test(`CLI SIGINT during ${phase} closes its real browser before exiting`, { timeout: 100_000 }, async (t) => {
  const upstream = (process.env.NOTTE_API_URL || 'https://api.notte.cc').replace(/\/$/, '');
  let id = '';
  let child: ReturnType<typeof spawn>;
  let interrupted = false;
  let interruptedAt = 0;
  let mcpRequests = 0;
  const interrupt = () => { interrupted = true; interruptedAt = Date.now(); child.kill('SIGINT'); };
  const server = createServer(async (req, res) => {
    let body = '';
    for await (const part of req) body += part.toString();
    if (req.url === '/mcp') {
      mcpRequests++;
      if (phase === 'mcp') interrupt();
      return; // Keep the real native MCP initialization pending until its signal aborts.
    }
    try {
      const headers = new Headers();
      for (const [name, value] of Object.entries(req.headers)) {
        if (value !== undefined && !['host', 'connection', 'content-length'].includes(name)) headers.set(name, String(value));
      }
      const response = await fetch(`${upstream}${req.url}`, { method: req.method, headers, body: body || undefined, signal: AbortSignal.timeout(30_000), redirect: 'error' });
      const text = await response.text();
      if (req.method === 'POST' && req.url?.startsWith('/sessions') && response.ok) {
        const value = JSON.parse(text);
        if (value.session_id) id = value.session_id;
        if (phase === 'claim' && !interrupted && id) {
          interrupt();
          await sleep(100); // Deliver SIGINT while Session.use still awaits the claim response.
        }
      }
      res.writeHead(response.status, { 'Content-Type': response.headers.get('content-type') ?? 'application/json' });
      res.end(text);
    } catch {
      res.writeHead(502); res.end('{}');
    }
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => { server.closeAllConnections(); return new Promise<void>((resolve) => server.close(() => resolve())); });
  const port = (server.address() as AddressInfo).port;
  child = spawn(process.execPath, [fileURLToPath(new URL('../demo.ts', import.meta.url))], {
    env: { ...process.env, NOTTE_API_URL: `http://127.0.0.1:${port}`, PIPEDREAM_CLIENT_ID: 'fixture-client',
      PIPEDREAM_CLIENT_SECRET: 'fixture-secret', PIPEDREAM_PROJECT_ID: 'proj_fixture', // pragma: allowlist secret
      PIPEDREAM_EXTERNAL_USER_ID: 'user-fixture', PIPEDREAM_ACTION_FILE: '' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const timeout = setTimeout(() => child.kill('SIGKILL'), 80_000);
  t.after(() => { clearTimeout(timeout); if (child.exitCode === null) child.kill('SIGKILL'); });
  let output = '';
  child.stdout!.on('data', (part) => { output += part.toString(); });
  child.stderr!.on('data', (part) => { output += part.toString(); });
  const [code, signal] = await once(child, 'exit');
  assert.equal(interrupted, true, 'CLI must receive SIGINT after an actual browser claim');
  assert.ok(Date.now() - interruptedAt < 30_000, 'Signal must interrupt initialization before the native MCP60s timeout');
  if (phase === 'claim') assert.equal(mcpRequests, 0, 'Already-aborted initialization must send no MCP request');
  assert.equal(code, 130);
  assert.equal(signal, null);
  assert.ok(id, 'Proxy must capture the actual allocated browser ID');
  assert.ok(output.includes(id), 'Safe cancellation error must retain the owned browser ID');
  assert.doesNotMatch(output, /fixture-secret|fixture-private-argument|fixture-access-token/);
  assert.ok(!output.includes(process.env.NOTTE_API_KEY!));
  const row = await closed(id);
  assert.ok(!row.steps.some((step) => step.type === 'execution_result'), 'Interrupted initialization must run no browser action');
  console.log(`CLI SIGINT during ${phase}: owned browser ${id} independently closed`);
});
}
