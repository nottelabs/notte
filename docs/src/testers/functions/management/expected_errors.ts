// @sniptest filename=expected_errors.ts
// @sniptest show=3-13
const functionId = process.env.NOTTE_FUNCTION_ID!;

import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const fn = client.NotteFunction({ function_id: functionId });

// Runs that raise these classes, or a subclass of them, end as "rejected"
const { expected_errors } = await fn.updateMetadata({ expected_errors: ['AccountNotUnique', 'StaffReviewRequired'] });
console.log(expected_errors);

// An empty list turns it off again
const cleared = await fn.updateMetadata({ expected_errors: [] });

const results = [expected_errors, cleared.expected_errors];
export { results };
