import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { inspect } from 'node:util';
import { test } from 'node:test';
import { withBrowser } from '../src/main.ts';

test('transport rejection retains HTTP status and step without provider secrets', async () => {
  const sentinel = 'test-only-private-provider-detail';
  const server = createServer((_request, response) => {
    response.writeHead(401);
    response.end(`Bearer ${sentinel}`);
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  assert.ok(address && typeof address !== 'string');
  const previous = { token: process.env.NOTTE_API_KEY, url: process.env.NOTTE_API_URL };
  process.env.NOTTE_API_KEY = sentinel;
  process.env.NOTTE_API_URL = `http://127.0.0.1:${address.port}`;
  try {
    await assert.rejects(withBrowser(async () => assert.fail('Unauthorized transport must not start a browser')), error => {
      assert.ok(error instanceof Error);
      assert.equal(error.message, 'Notte MCP connection failed (HTTP 401)');
      assert.ok(!inspect(error, { depth: 10 }).includes(sentinel));
      return true;
    });
  } finally {
    if (previous.token === undefined) delete process.env.NOTTE_API_KEY;
    else process.env.NOTTE_API_KEY = previous.token;
    if (previous.url === undefined) delete process.env.NOTTE_API_URL;
    else process.env.NOTTE_API_URL = previous.url;
    await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  }
});
