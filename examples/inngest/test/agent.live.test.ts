import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { ToolResultPayload } from '@inngest/agent-kit';
import { NotteClient, sessionStatus } from 'notte-sdk';
import { browserAgent, readPage } from '../src/agent.ts';

const live = process.env.NOTTE_INNGEST_LIVE === '1';
const modelLive = process.env.NOTTE_INNGEST_MODEL_LIVE === '1';

async function trackSessions(run: () => Promise<void>) {
  assert.ok(process.env.NOTTE_API_KEY);
  assert.ok(process.env.NOTTE_API_URL, 'Choose the test API explicitly');
  const original = globalThis.fetch;
  const ids: string[] = [];
  globalThis.fetch = async (input, options) => {
    const response = await original(input, options);
    const url = new URL(input instanceof Request ? input.url : String(input));
    if (url.pathname === '/sessions/start' && response.ok) {
      ids.push(((await response.clone().json()) as { session_id: string }).session_id);
    }
    return response;
  };
  try {
    await run();
  } finally {
    globalThis.fetch = original;
    assert.equal(ids.length, 1, 'Expected exactly one owned browser');
    const client = new NotteClient();
    let stopped = false;
    for (let attempt = 0; attempt < 30; attempt++) {
      const response = await sessionStatus({
        client: client.getClient(), path: { session_id: ids[0] }, throwOnError: true,
        signal: AbortSignal.timeout(15_000),
      });
      if (response.data.status === 'closed') {
        stopped = true;
        break;
      }
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    assert.ok(stopped, 'The owned browser did not close');
  }
}

test('AgentKit browser integration', { skip: !live, timeout: 180_000 }, async t => {
  await t.test('reads the title and closes its browser', () => trackSessions(async () => {
    const result = await readPage({ url: 'https://example.com' });
    assert.equal(result.title, 'Example Domain');
  }));
  await t.test('closes its browser after navigation failure', () => trackSessions(async () => {
    await assert.rejects(readPage({ url: 'https://missing.notte.invalid' }), /failed during navigation/);
  }));
  await t.test('the real model calls the browser tool', { skip: !modelLive }, () => trackSessions(async () => {
    assert.ok(process.env.ANTHROPIC_API_KEY);
    const result = await browserAgent.run('Read the title of https://example.com');
    assert.equal(result.toolCalls.length, 1);
    assert.equal(result.toolCalls[0].tool.name, 'page_title');
    const content = result.toolCalls[0].content as ToolResultPayload<{ title: string }>;
    assert.equal(content.data.title, 'Example Domain');
  }));
});
