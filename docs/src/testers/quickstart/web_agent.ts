import { NotteClient } from 'notte-sdk';

const client = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY,
});

await client.Session({ open_viewer: true }).use(async (session) => {
  const agent = client.Agent({ session, max_steps: 5 });

  const response = await agent.run({
    task: 'Browse on Notte docs and book a demo for me',
    url: 'https://docs.notte.cc',
  });

  console.log(response);
});
