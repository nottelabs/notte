// @sniptest filename=deletion_protection.ts
// @sniptest show=3-13
const functionId = process.env.NOTTE_FUNCTION_ID!;

import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const fn = client.NotteFunction({ function_id: functionId });

// Protect the function: deletes are refused until this is turned off
const { deletion_protected } = await fn.updateMetadata({ deletion_protected: true });
console.log(deletion_protected);

// Turning it off takes the key of a workspace admin or owner
const released = await fn.updateMetadata({ deletion_protected: false });

const results = [deletion_protected === true && released.deletion_protected === false];
export { results };
