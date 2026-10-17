import assert from 'node:assert/strict';
import { test } from 'node:test';
import { NotteClient, sessionStatus } from 'notte-sdk';
import { capturePage } from '../src/main.ts';

test('actual capture closes its owned Notte browser', { skip: process.env.NOTTE_BOX_CAPTURE_LIVE !== '1', timeout: 120_000 }, async () => {
  assert.ok(process.env.NOTTE_API_URL, 'Choose the test API explicitly');
  const original = globalThis.fetch;
  const ids: string[] = [];
  globalThis.fetch = async (input, options) => {
    const response = await original(input, options);
    const url = new URL(input instanceof Request ? input.url : String(input));
    if (url.pathname === '/sessions/start' && response.ok) ids.push((await response.clone().json()).session_id);
    return response;
  };
  try {
    const { image, sessionId } = await capturePage();
    assert.ok(image.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])));
    assert.ok(image.length > 1000);
    assert.deepEqual(ids, [sessionId]);
  } finally {
    globalThis.fetch = original;
    assert.equal(ids.length, 1);
    const client = new NotteClient();
    let closed = false;
    for (let attempt = 0; attempt < 30; attempt++) {
      const result = await sessionStatus({ client: client.getClient(), path: { session_id: ids[0] }, throwOnError: true, signal: AbortSignal.timeout(15_000) });
      if (result.data.status === 'closed') { closed = true; break; }
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    assert.ok(closed, 'Owned browser did not close');
  }
});
