import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { test } from 'node:test';
import { activityInfo } from '@temporalio/activity';
import { WorkflowFailedError } from '@temporalio/client';
import { TestWorkflowEnvironment } from '@temporalio/testing';
import { Worker } from '@temporalio/worker';
import { NotteClient, sessionStatus } from 'notte-sdk';
import { readPage } from '../src/activities';
import { readNottePage } from '../src/workflows';

test('Temporal runs Notte browser activities', {
  skip: process.env.NOTTE_TEMPORAL_LIVE !== '1', timeout: 240_000,
}, async t => {
  assert.ok(process.env.NOTTE_API_KEY);
  assert.ok(process.env.NOTTE_API_URL, 'Choose the browser API explicitly');
  const env = await TestWorkflowEnvironment.createLocal();
  const taskQueue = `notte-test-${randomUUID()}`;
  const original = globalThis.fetch;
  const sessions: string[] = [];
  const attempts: number[] = [];
  globalThis.fetch = async (input, options) => {
    const response = await original(input, options);
    const url = new URL(input instanceof Request ? input.url : String(input));
    if (url.pathname === '/sessions/start' && response.ok) {
      sessions.push(((await response.clone().json()) as { session_id: string }).session_id);
    }
    return response;
  };
  try {
    const worker = await Worker.create({
      connection: env.nativeConnection, taskQueue, workflowsPath: require.resolve('../src/workflows'),
      activities: { readPage: async (payload: { url: string }) => {
        attempts.push(activityInfo().attempt);
        return readPage(payload);
      } },
    });
    await worker.runUntil(async () => {
      await t.test('returns the page title', async () => {
        const result = await env.client.workflow.execute(readNottePage, {
          args: ['https://example.com'], taskQueue, workflowId: randomUUID(),
        });
        assert.equal(result.title, 'Example Domain');
        assert.deepEqual(sessions, [result.session_id]);
      });
      await t.test('retries navigation failure three times', async () => {
        await assert.rejects(env.client.workflow.execute(readNottePage, {
          args: ['https://missing.notte.invalid'], taskQueue, workflowId: randomUUID(),
        }), WorkflowFailedError);
        assert.deepEqual(attempts, [1, 1, 2, 3]);
        assert.equal(new Set(sessions).size, 4);
      });
    });
  } finally {
    globalThis.fetch = original;
    try {
      const client = new NotteClient();
      for (const sessionId of sessions) {
        const response = await sessionStatus({
          client: client.getClient(), path: { session_id: sessionId }, throwOnError: true,
          signal: AbortSignal.timeout(15_000),
        });
        assert.equal(response.data.status, 'closed', `Activity leaked session ${sessionId}`);
      }
    } finally {
      await env.teardown();
    }
  }
});
