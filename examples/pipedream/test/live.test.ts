import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import type { AddressInfo } from 'node:net';
import { test } from 'node:test';
import { setTimeout as sleep } from 'node:timers/promises';
import { runDemo } from '../demo.ts';

const config = { clientId: 'fixture-client', clientSecret: 'fixture-secret', projectId: 'proj_fixture', externalUserId: 'user-fixture' };

async function closed(id: string) {
  const api = process.env.NOTTE_API_URL ?? 'https://api.notte.cc';
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

for (const mode of ['success', 'oauth401', 'mcp401', 'navigation', 'cancel']) {
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
      const result = body.method === 'initialize'
        ? { protocolVersion: body.params.protocolVersion, capabilities: { tools: {} }, serverInfo: { name: 'local-pipedream-fixture', version: '1' } }
        : { tools: [{ name: 'fixture_catalog_read', description: 'Local discovery fixture, not a provider action', inputSchema: { type: 'object', properties: {} }, annotations: { readOnlyHint: true } }] };
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
    const run = runDemo(config, { providerFetch, signal: controller.signal, pageUrl: mode === 'navigation' ? 'https://notte-pipedream-missing.invalid' : 'https://example.com' });
    if (mode === 'success') {
      const result = await run;
      id = result.session_id;
      assert.match(JSON.stringify(result.page), /Example Domain/);
      assert.deepEqual(result.tool_names, ['fixture_catalog_read']);
    } else {
      try { await run; assert.fail('Expected the real failure'); }
      catch (error) {
        assert.ok(error instanceof Error);
        assert.doesNotMatch(error.message, /fixture-secret|fixture-access-token/);
        id = error.message.match(/session ([a-f0-9-]{36})/)![1];
      }
    }
    const row = await closed(id);
    assert.doesNotMatch(warnings.join('\n'), /fixture-secret|fixture-access-token/, 'Provider response details must stay out of SDK cleanup logs');
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
        assert.notEqual(request.body.method, 'tools/call', 'Discovery must never invoke vendor actions');
      }
    }
    console.log(`${mode}: owned browser ${id} independently closed`);
  });
}
