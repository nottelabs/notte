// @sniptest filename=invoke_function.ts
// @sniptest show=5-17
import assert from 'node:assert/strict';

const functionId = process.env.NOTTE_FUNCTION_ID!;

import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

// Get function by ID
const fn = client.NotteFunction({ function_id: functionId });

// Run function with parameters
const result = await fn.run({ url: 'https://example.com', search_query: 'laptop' });

console.log(result.result); // Access the return value
console.log(result.status); // "closed" or "failed"
console.log(result.session_id); // Session ID if created

assert.equal(result.function_id, functionId);
export { result };
