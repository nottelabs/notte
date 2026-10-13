// @sniptest filename=invoke_sdk.ts
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const fn = client.NotteFunction({ function_id: process.env.NOTTE_FUNCTION_ID! });

const result = await fn.run({ url: 'https://example.com', search_query: 'laptop' });

console.log(result.result);
