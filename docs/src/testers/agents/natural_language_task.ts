import { NotteClient } from 'notte-sdk';

const client = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY,
});

await client.Session().use(async (session) => {
  const agent = client.Agent({ session });
  await agent.run({
    task: 'Find the cheapest laptop under $1000 and add it to cart',
  });
});
