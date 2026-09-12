// @sniptest filename=get_function_details.ts
// @sniptest show=4-17
import assert from 'node:assert/strict';
const functionId = process.env.NOTTE_FUNCTION_ID!;

import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

// Get function by ID
const fn = client.NotteFunction({ function_id: functionId });
const response = await fn.get();

// Access function properties
console.log(`Function ID: ${response.function_id}`);
console.log(`Name: ${response.name}`);
console.log(`Description: ${response.description}`);
console.log(`Latest Version: ${response.latest_version}`);
console.log(`Versions: ${response.versions}`);

assert.equal(response.function_id, functionId);
assert.ok(response.versions.includes(response.latest_version));
const results = [response.function_id === functionId, response.versions.length > 0];
export { results };
