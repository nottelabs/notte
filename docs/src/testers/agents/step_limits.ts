import { NotteClient } from 'notte-sdk';

const client = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY,
});

await client.Session().use(async (session) => {
  const agent = client.Agent({ session });
  await agent.run({
    task: 'Find and summarize the top 5 AI news from today',
    max_steps: 20, // Limit to 20 actions
  });
});
