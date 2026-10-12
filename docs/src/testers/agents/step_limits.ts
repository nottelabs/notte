import { NotteClient } from 'notte-sdk';

const client = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY,
});

await client.Session().use(async (session) => {
  const agent = client.Agent({ session, max_steps: 10 }); // Stop after at most 10 steps
  await agent.run({ task: 'Find and summarize the top 5 AI news from today' });
});
