import assert from 'node:assert/strict';
import { test } from 'node:test';
import { setTimeout } from 'node:timers/promises';
import { NotteClient, sessionStatus } from 'notte-sdk';
import { readPage } from '../src/trigger/read-page.ts';

const live = process.env.NOTTE_TRIGGER_LIVE === '1';

async function closed(sessionId: string) {
  const client = new NotteClient();
  for (let attempt = 0; attempt < 30; attempt++) {
    const response = await sessionStatus({
      client: client.getClient(), path: { session_id: sessionId }, throwOnError: true,
      signal: AbortSignal.timeout(15_000),
    });
    if (response.data.status === 'closed') return;
    await setTimeout(500);
  }
  assert.fail('The owned browser did not close');
}

async function trackSessions(run: () => Promise<void>) {
  const original = globalThis.fetch;
  const ids: string[] = [];
  globalThis.fetch = async (input, options) => {
    const response = await original(input, options);
    const url = new URL(input instanceof Request ? input.url : String(input));
    if (url.pathname === '/sessions/start' && response.ok) {
      const body = await response.clone().json() as { session_id: string };
      ids.push(body.session_id);
    }
    return response;
  };
  try {
    await run();
  } finally {
    globalThis.fetch = original;
    assert.equal(ids.length, 1, 'The task should create exactly one owned browser');
    await closed(ids[0]);
  }
}

test('Trigger task browser handler', { skip: !live, timeout: 120_000 }, async (t) => {
  assert.ok(process.env.NOTTE_API_KEY);
  assert.ok(process.env.NOTTE_API_URL, 'Choose the test API explicitly');
  await t.test('reads the page and closes its browser', () => trackSessions(async () => {
    const result = await readPage({ url: 'https://example.com' });
    assert.equal(result.title, 'Example Domain');
    assert.ok(result.session_id);
  }));
  await t.test('closes its browser when navigation fails', () => trackSessions(async () => {
    await assert.rejects(readPage({ url: 'https://missing.notte.invalid' }), /Notte browser task failed during navigation/);
  }));
});
