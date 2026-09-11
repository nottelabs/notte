// @sniptest filename=check_run_status.ts
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const fn = client.NotteFunction({
  function_id: process.env.NOTTE_FUNCTION_ID!,
});

const result = await fn.run({ url: 'https://example.com' });
// Retrieve a run owned by this example, rather than a placeholder ID.
const runStatus = await fn.getRun(result.function_run_id);
console.log(
  JSON.stringify({
    status: runStatus.status,
    same_run: runStatus.function_run_id === result.function_run_id,
  }),
);
