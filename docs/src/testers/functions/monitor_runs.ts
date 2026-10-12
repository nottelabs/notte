// @sniptest filename=monitor_runs.ts
// @sniptest show=5-32
import assert from 'node:assert/strict';

const functionId = process.env.NOTTE_FUNCTION_ID!;

import { setTimeout as sleep } from 'node:timers/promises';
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const fn = client.NotteFunction({ function_id: functionId });

// Create the run first so you know its ID
const { function_run_id: runId } = await fn.createRun();

// Start it without awaiting: run() resolves only when the run finishes
const execution = fn.run({ url: 'https://example.com' }, { functionRunId: runId, stream: false });

// Poll status while it runs
while (true) {
  const status = await fn.getRun(runId);

  console.log(`Status: ${status.status}`);

  if (status.status === 'closed' || status.status === 'failed') {
    console.log('Final result:', status.result);
    break;
  }

  await sleep(5000); // Check every 5 seconds
}

await execution;

const runStatus = await fn.getRun(runId);
assert.equal(runStatus.status, 'closed');
assert.deepEqual(JSON.parse(runStatus.result!), { url: 'https://example.com', search_query: '' });
export { runStatus as run_status, runId as run_id };
