// @sniptest filename=version_management.ts
// @sniptest show=5-16
import assert from 'node:assert/strict';

const functionId = process.env.NOTTE_FUNCTION_ID!;

import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const fn = client.NotteFunction({ function_id: functionId });
const response = await fn.get();

// Get all versions
console.log('Available versions:', response.versions);

// Get latest version
console.log(`Latest: ${response.latest_version}`);

assert.equal(response.function_id, functionId);
const results = [response.versions.length > 0, response.versions.includes(response.latest_version)];
export { results };
