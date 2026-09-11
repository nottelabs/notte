// @sniptest filename=stream_sdk.ts
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const fn = client.NotteFunction({
  function_id: process.env.NOTTE_FUNCTION_ID!,
});

// Stream logs while waiting for the final result.
const result = await fn.run({ url: 'https://example.com' }, { stream: true });
console.log(JSON.stringify({ status: result.status, result: result.result }));
