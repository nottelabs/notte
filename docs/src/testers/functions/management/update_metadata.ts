// @sniptest filename=update_metadata.ts
// @sniptest show=3-10
const functionId = process.env.NOTTE_FUNCTION_ID!;

import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const fn = client.NotteFunction({ function_id: functionId });
await fn.updateMetadata({ name: 'Price monitor', description: 'Checks competitor prices' });
const metadata = await fn.get();
console.log(metadata.name);

if (metadata.name !== 'Price monitor') throw new Error('Metadata was not saved');
const results = [metadata.name === 'Price monitor'];
export { results };
