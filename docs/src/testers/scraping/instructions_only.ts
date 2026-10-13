import { NotteClient } from 'notte-sdk';

const client = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY,
});

const result = await client.scrape('https://example.com/article', {
  instructions: 'Extract the article title, author, and publication date',
});

console.log(result);
