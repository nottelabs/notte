// @sniptest filename=check_run_status.ts
// @sniptest show=11-14
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const fn = client.NotteFunction({
  function_id: process.env.NOTTE_FUNCTION_ID!,
});

const result = await fn.run({ url: 'https://example.com' });
const runId = result.function_run_id;

const runStatus = await fn.getRun(runId);

console.log(`Status: ${runStatus.status}`); // "active", "closed", "failed"
console.log(`Result: ${runStatus.result}`);

console.log(
  JSON.stringify({
    status: runStatus.status,
    same_run: runStatus.function_run_id === result.function_run_id,
  }),
);
