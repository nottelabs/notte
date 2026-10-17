import assert from 'node:assert/strict';
import { test } from 'node:test';
import { setTimeout as sleep } from 'node:timers/promises';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

const key = process.env.NOTTE_API_KEY;
assert.ok(key, 'Set NOTTE_API_KEY before running live MCP tests');
const api = (process.env.NOTTE_API_URL ?? 'https://api.notte.cc').replace(/\/$/, '');
const headers = { Authorization: `Bearer ${key}` };

function data(result) {
  if (result.structuredContent) return result.structuredContent;
  const text = result.content.find(block => block.type === 'text')?.text;
  return text ? JSON.parse(text) : {};
}

async function assertClosed(id) {
  const deadline = Date.now() + 15_000;
  while (true) {
    const response = await fetch(`${api}/sessions/${id}`, { headers, signal: AbortSignal.timeout(15_000) });
    assert.equal(response.status, 200, 'Independent session lookup failed');
    const { status } = await response.json();
    if (status === 'closed') return;
    assert.equal(status, 'active', 'Unexpected session state');
    assert.ok(Date.now() < deadline, `Owned browser ${id} remained active`);
    await sleep(500);
  }
}

for (const failure of [false, true]) {
  test(`hosted MCP browser ${failure ? 'failure' : 'success'} and cleanup`, { timeout: 90_000 }, async () => {
    const transport = new StreamableHTTPClientTransport(new URL(`${api}/mcp`), { requestInit: { headers } });
    const client = new Client({ name: 'notte-replit-contract-test', version: '1.0.0' });
    let id;
    try {
      await client.connect(transport);
      const { tools } = await client.listTools();
      for (const name of ['manage_browsers', 'browser_action', 'browser_observe', 'browser_scrape']) {
        assert.ok(tools.some(tool => tool.name === name), `Missing advertised tool ${name}`);
      }
      assert.equal(tools.find(tool => tool.name === 'browser_scrape').annotations.readOnlyHint, true);
      const started = await client.callTool({ name: 'manage_browsers', arguments: { action: 'start', max_duration_minutes: 3 } });
      assert.ok(!started.isError, 'Browser creation failed');
      id = data(started).browser_id;
      assert.match(id, /^[a-f0-9-]{36}$/, 'MCP must return its owned browser ID');
      const navigation = await client.callTool({ name: 'browser_action', arguments: {
        browser_id: id, action: { type: 'goto', url: failure ? 'https://notte-replit-missing.invalid' : 'https://example.com' },
      } });
      if (failure) {
        assert.ok(navigation.isError || data(navigation).success === false, 'An actual browser DNS failure must surface in the tool result');
      } else {
        assert.ok(!navigation.isError, 'Browser navigation failed');
        assert.equal(data(navigation).success, true, 'Browser action did not succeed');
        const scraped = await client.callTool({ name: 'browser_scrape', arguments: { browser_id: id } });
        assert.ok(!scraped.isError, 'Plain page scrape failed');
        assert.match(JSON.stringify(data(scraped)), /Example Domain/);
      }
    } finally {
      try {
        if (id) {
          try {
            const stopped = await client.callTool({ name: 'manage_browsers', arguments: { action: 'stop', browser_id: id } });
            assert.ok(!stopped.isError, `MCP could not stop its owned browser ${id}`);
          } catch (error) {
            // Release this test's browser if the MCP connection itself failed; retain the failing assertion.
            await fetch(`${api}/sessions/${id}/stop`, { method: 'DELETE', headers, signal: AbortSignal.timeout(15_000) });
            throw error;
          } finally { await assertClosed(id); }
        }
      } finally { await client.close(); }
    }
  });
}
