import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { test } from 'node:test';
import { inspect } from 'node:util';
import { notte } from '../src/notte.ts';

test('real SDK authentication failures expose a status without the response body', { timeout: 15_000 }, async () => {
  const token = 'fixture-token';
  let authorized = false;
  const server = createServer((request, response) => {
    authorized = request.headers.authorization === `Bearer ${token}`;
    response.writeHead(401, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify({ detail: `Refused token ${token}` }));
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  try {
    const address = server.address();
    assert.ok(address && typeof address === 'object');
    await assert.rejects(notte().acquire({
      runId: 'authentication-check', targetName: 'notte', slot: 0, slots: 1,
      env: { NOTTE_API_KEY: token, NOTTE_API_URL: `http://127.0.0.1:${address.port}` },
      signal: AbortSignal.timeout(10_000), log() {},
    }), (error: unknown) => error instanceof Error && error.message.includes('HTTP 401') && !error.message.includes(token));
    assert.ok(authorized, 'The provider must use the request environment');
  } finally {
    await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
});

test('acquisition and cleanup failures retain both statuses without private bodies', { timeout: 15_000 }, async () => {
  const id = '00000000-0000-4000-8000-000000000001';
  const token = 'fixture-token';
  const calls: string[] = [];
  const server = createServer((request, response) => {
    const path = new URL(request.url!, 'http://localhost').pathname;
    calls.push(`${request.method} ${path}`);
    response.setHeader('Content-Type', 'application/json');
    if (path === '/sessions/start') {
      response.end(JSON.stringify({ session_id: id, status: 'active' }));
    } else {
      response.writeHead(request.method === 'DELETE' ? 503 : 500);
      response.end(JSON.stringify({ detail: `PRIVATE_PROVIDER_BODY ${token}` }));
    }
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const address = server.address();
    assert.ok(address && typeof address === 'object');
    await assert.rejects(notte().acquire({
      runId: 'cleanup-check', targetName: 'notte', slot: 0, slots: 1,
      env: { NOTTE_API_KEY: token, NOTTE_API_URL: `http://127.0.0.1:${address.port}` },
      signal: AbortSignal.timeout(10_000), log() {},
    }), (error: unknown) => {
      assert.ok(error instanceof Error);
      assert.ok(error.message.includes('acquisition failed: HTTP 500'), 'The primary failure was replaced');
      assert.ok(error.message.includes('cleanup failed: HTTP 503'));
      assert.ok(error.message.includes(id));
      const diagnostic = inspect(error, { depth: 10 });
      assert.ok(!diagnostic.includes(token));
      assert.ok(!diagnostic.includes('PRIVATE_PROVIDER_BODY'));
      return true;
    });
    assert.deepEqual(calls.slice(0, 2), ['POST /sessions/start', `GET /sessions/${id}/debug`]);
    assert.ok(calls.length >= 3, 'The acquired browser must receive a cleanup request');
    assert.ok(calls.slice(2).every(call => call === `DELETE /sessions/${id}/stop`), 'Retries must stop only the acquired browser');
  } finally {
    await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  }
});
