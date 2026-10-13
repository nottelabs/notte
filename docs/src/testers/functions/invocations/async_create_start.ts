// @sniptest filename=async_create_start.ts
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const fn = client.NotteFunction({ function_id: process.env.NOTTE_FUNCTION_ID! });

// Optional: create a run record when you need its ID before execution.
const created = await fn.createRun();
console.log(`Run created: ${created.function_run_id}`);

// Execute that run and wait for its result. Omit functionRunId to create a new run.
const result = await fn.run(
  { url: 'https://example.com' },
  { functionRunId: created.function_run_id },
);
console.log(result.result);
const run = await fn.getRun(created.function_run_id);
console.log(run.status);
