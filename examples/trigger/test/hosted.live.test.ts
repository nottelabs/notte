import assert from 'node:assert/strict';
import { test } from 'node:test';
import { runs, tasks } from '@trigger.dev/sdk';
import { NotteClient, sessionStatus } from 'notte-sdk';
import type { readNottePage } from '../src/trigger/read-page.ts';

const live = process.env.NOTTE_TRIGGER_HOSTED_LIVE === '1';

test('Trigger.dev executes the registered browser task', { skip: !live, timeout: 180_000 }, async () => {
  assert.ok(process.env.TRIGGER_SECRET_KEY);
  assert.ok(process.env.NOTTE_API_KEY);
  assert.ok(process.env.NOTTE_API_URL, 'Choose the browser API explicitly');
  const handle = await tasks.trigger<typeof readNottePage>('notte-read-page', { url: 'https://example.com' }, {
    ttl: '1m', maxAttempts: 1,
  });
  try {
    const deadline = Date.now() + 90_000;
    let result = await runs.retrieve<typeof readNottePage>(handle.id, { retry: { maxAttempts: 1 } });
    while (!result.isCompleted && Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 500));
      result = await runs.retrieve<typeof readNottePage>(handle.id, { retry: { maxAttempts: 1 } });
    }
    assert.equal(result.status, 'COMPLETED');
    assert.equal(result.output?.title, 'Example Domain');
    assert.ok(result.output?.session_id);
    const client = new NotteClient();
    for (let attempt = 0; attempt < 30; attempt++) {
      const response = await sessionStatus({
        client: client.getClient(), path: { session_id: result.output.session_id }, throwOnError: true,
        signal: AbortSignal.timeout(15_000),
      });
      if (response.data.status === 'closed') return;
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    assert.fail('The hosted task did not close its browser');
  } finally {
    const result = await runs.retrieve(handle.id);
    if (!result.isCompleted) await runs.cancel(handle.id);
  }
});
