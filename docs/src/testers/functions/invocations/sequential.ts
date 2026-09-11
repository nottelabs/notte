// @sniptest filename=sequential.ts
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const fn = client.NotteFunction({
  function_id: process.env.NOTTE_FUNCTION_ID!,
});

const urls = ['https://example.com', 'https://example.org'];
const results: unknown[] = [];
for (const url of urls) {
  const result = await fn.run({ url });
  results.push(result.result);
}
console.log(JSON.stringify({ results }));
