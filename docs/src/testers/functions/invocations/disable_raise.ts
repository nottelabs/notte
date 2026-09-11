// @sniptest filename=disable_raise.ts
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const fn = client.NotteFunction({
  function_id: process.env.NOTTE_FUNCTION_ID!,
});

// Inspect a failed run without throwing an exception.
const result = await fn.run(
  { url: 'https://example.com', fail: true },
  { raiseOnFailure: false },
);
console.log(JSON.stringify({ status: result.status }));
