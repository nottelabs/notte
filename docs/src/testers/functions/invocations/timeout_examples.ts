// @sniptest filename=timeout_examples.ts
// @sniptest show=5-14
import assert from 'node:assert/strict';

const functionId = process.env.NOTTE_FUNCTION_ID!;

import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const fn = client.NotteFunction({ function_id: functionId });

// Short task
let result = await fn.run({ url: 'https://example.com' }, { timeoutMs: 60_000 });

// Long task
result = await fn.run({ url: 'https://example.com' }, { timeoutMs: 600_000 });

assert.equal(result.status, 'closed');
assert.deepEqual(result.result, { url: 'https://example.com', search_query: '' });
export { result };
