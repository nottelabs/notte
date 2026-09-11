// @sniptest filename=cloud_execution.ts
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const fn = client.NotteFunction({
  function_id: process.env.NOTTE_FUNCTION_ID!,
});

// Run on Notte infrastructure (the default).
const result = await fn.run({ url: 'https://example.com' });
console.log(JSON.stringify({ status: result.status, result: result.result }));
