// @sniptest filename=high_failure_rate.ts
// @sniptest show=12-28
import assert from 'node:assert/strict';
import { NotteClient as FixtureClient } from 'notte-sdk';

const functionId = process.env.NOTTE_FUNCTION_ID!;
const failed = await new FixtureClient().NotteFunction({ function_id: functionId }).run(
  { url: 'https://example.com', fail: true },
  { raiseOnFailure: false, stream: false },
);
assert.equal(failed.status, 'failed');


import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const fn = client.NotteFunction({ function_id: functionId });
const runs = await fn.runs({ only_active: false });
const failures = runs.items.filter(run => run.status === 'failed');

console.log(`Failed runs: ${failures.length}/${runs.items.length}`);

// Analyze failure reasons
for (const run of failures.slice(0, 5)) { // Last 5 failures
  const runDetail = await fn.getRun(run.function_run_id);
  console.log(`Run ${run.function_run_id}:`);
  console.log(`  Error: ${runDetail.result}`);
  console.log(`  Time: ${run.created_at}`);
}

const matched = failures.slice(0, 5).filter(run => run.function_run_id === failed.function_run_id);
assert.equal(matched.length, 1, `Seeded failed run ${failed.function_run_id}; listed ${runs.items.map(run => `${run.function_run_id}:${run.status}`).join(', ')}`);
const ownedDetail = await fn.getRun(failed.function_run_id);
assert.ok(String(ownedDetail.result).includes('Example function failure'));
const results = [matched[0].status, String(ownedDetail.result).includes('Example function failure')];
export { results };
