import assert from 'node:assert/strict';
import { test } from 'node:test';
import { runs, tasks } from '@trigger.dev/sdk';
import { NotteClient, sessionStatus } from 'notte-sdk';
import type { readNottePage } from '../src/trigger/read-page.ts';

const live = process.env.NOTTE_TRIGGER_HOSTED_LIVE === '1';

async function execute(url: string, maxAttempts: number) {
  assert.ok(process.env.TRIGGER_SECRET_KEY);
  assert.ok(process.env.NOTTE_API_KEY);
  assert.ok(process.env.NOTTE_API_URL, 'Choose the browser API explicitly');
  const handle = await tasks.trigger<typeof readNottePage>('notte-read-page', { url }, {
    ttl: '1m', maxAttempts,
  });
  try {
    const deadline = Date.now() + 90_000;
    let result = await runs.retrieve<typeof readNottePage>(handle.id, { retry: { maxAttempts: 1 } });
    while (!result.isCompleted && Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 500));
      result = await runs.retrieve<typeof readNottePage>(handle.id, { retry: { maxAttempts: 1 } });
    }
    assert.ok(result.isCompleted, `Run did not finish: ${handle.id}`);
    return result;
  } finally {
    const result = await runs.retrieve(handle.id);
    if (!result.isCompleted) await runs.cancel(handle.id);
  }
}

async function closed(sessionId: string) {
  const client = new NotteClient();
  const signal = AbortSignal.timeout(15_000);
  while (!signal.aborted) {
    const response = await sessionStatus({
      client: client.getClient(), path: { session_id: sessionId }, throwOnError: true,
      signal,
    });
    if (response.data.status === 'closed') return;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  assert.fail('The hosted task did not close its browser');
}

test('Trigger.dev executes the registered browser task', { skip: !live, timeout: 180_000 }, async () => {
  const result = await execute('https://example.com', 1);
  assert.equal(result.status, 'COMPLETED');
  assert.equal(result.output?.title, 'Example Domain');
  assert.ok(result.output?.session_id);
  await closed(result.output.session_id);
});

test('Trigger.dev retries navigation failures and closes the final browser', { skip: !live, timeout: 180_000 }, async () => {
  const result = await execute('https://missing.notte.invalid', 3);
  assert.equal(result.status, 'FAILED');
  assert.equal(result.attemptCount, 3);
  const message = result.error?.message ?? '';
  assert.match(message, /failed during navigation/);
  assert.doesNotMatch(message, /https?:|wss?:|api_key/i);
  const sessionId = message.match(/session ([0-9a-f-]{36})/)?.[1];
  assert.ok(sessionId, 'Failure should identify its owned browser');
  await closed(sessionId);
});
