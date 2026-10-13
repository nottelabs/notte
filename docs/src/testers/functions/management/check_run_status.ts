// @sniptest filename=check_run_status.ts
// @sniptest show=10-19
import assert from 'node:assert/strict';

const functionId = process.env.NOTTE_FUNCTION_ID!;

import { NotteClient as FixtureClient } from 'notte-sdk';

const completed = await new FixtureClient().NotteFunction({ function_id: functionId }).run({ url: 'https://example.com' }, { stream: false });
const runId = completed.function_run_id;

import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

// Get run details
const runStatus = await client.NotteFunction({ function_id: functionId }).getRun(runId);

console.log(`Status: ${runStatus.status}`); // "active", "closed", "failed"
console.log('Result:', runStatus.result);
console.log(`Session ID: ${runStatus.session_id}`);

assert.equal(runStatus.status, 'closed');
assert.deepEqual(JSON.parse(runStatus.result!), { url: 'https://example.com', search_query: '' });
export { runStatus as run_status, runId as run_id };
