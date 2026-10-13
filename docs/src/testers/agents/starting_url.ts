const agent = client.Agent({ session });

await agent.run({
  task: 'Find pricing information',
  url: 'https://example.com/products',
});
