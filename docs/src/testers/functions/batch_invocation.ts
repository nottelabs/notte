// @sniptest filename=batch_invocation.ts
// @sniptest show=5-22
import assert from 'node:assert/strict';

const functionId = process.env.NOTTE_FUNCTION_ID!;

import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const fn = client.NotteFunction({ function_id: functionId });

const urls = ['https://site1.com', 'https://site2.com', 'https://site3.com'];

async function invokeFunction(url: string) {
  return fn.run({ url });
}

// Run in parallel
const results = await Promise.all(urls.map(invokeFunction));

for (const result of results) {
  console.log(result.result);
}

assert.ok(results.every(result => result.status === 'closed'));
assert.deepEqual(results.map(result => result.result), urls.map(url => ({ url, search_query: '' })));
assert.equal(new Set(results.map(result => result.function_run_id)).size, urls.length);
const capturedResults = results.map(result => result.result);
export { capturedResults as results };
