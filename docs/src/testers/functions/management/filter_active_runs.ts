// @sniptest filename=filter_active_runs.ts
// @sniptest show=8-19
import assert from 'node:assert/strict';
import { NotteClient as FixtureClient } from 'notte-sdk';

const functionId = process.env.NOTTE_FUNCTION_ID!;
const fixture = new FixtureClient().NotteFunction({ function_id: functionId });
const completed = await fixture.run({ url: 'https://example.com' }, { stream: false });

import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

// Get only active runs
const activeRuns = await client.NotteFunction({ function_id: functionId }).runs({ only_active: true });

console.log(`Active runs: ${activeRuns.items.length}`);

for (const run of activeRuns.items) {
  console.log(`Run ${run.function_run_id} - ${run.status}`);
}

const history = await fixture.runs({ only_active: false });
assert.ok(history.items.some(run => run.function_run_id === completed.function_run_id));
const results = activeRuns.items.map(run => run.status);
assert.deepEqual(results, []);
export { results };
