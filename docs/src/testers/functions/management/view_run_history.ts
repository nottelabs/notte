// @sniptest filename=view_run_history.ts
// @sniptest show=8-23
import assert from 'node:assert/strict';
import { NotteClient as FixtureClient } from 'notte-sdk';

const functionId = process.env.NOTTE_FUNCTION_ID!;
const fixture = new FixtureClient().NotteFunction({ function_id: functionId });
const completed = await fixture.run({ url: 'https://example.com' }, { stream: false });

import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

// Get recent runs
const runs = await client.NotteFunction({ function_id: functionId }).runs({
  only_active: false, // Include completed runs
});

for (const run of runs.items) {
  console.log(`Run ID: ${run.function_run_id}`);
  console.log(`Status: ${run.status}`);
  console.log(`Created: ${run.created_at}`);
  console.log(`Updated: ${run.updated_at}`);
  console.log('---');
}

const matched = runs.items.filter(run => run.function_run_id === completed.function_run_id);
assert.equal(matched.length, 1);
assert.equal(matched[0].status, 'closed');
const results = matched.map(run => run.status);
export { results };
