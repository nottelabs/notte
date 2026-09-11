// @sniptest filename=stream_sdk.ts
// @sniptest show=8-9
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const fn = client.NotteFunction({
  function_id: process.env.NOTTE_FUNCTION_ID!,
});

// Stream logs while waiting for the final result.
const result = await fn.run({ url: 'https://example.com' }, { stream: true });

export { result };
