import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { test } from 'node:test';
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
