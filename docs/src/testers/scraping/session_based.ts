import { NotteClient } from 'notte-sdk';

const client = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY,
});

await client.Session().use(async (session) => {
  // Navigate and authenticate
  await session.execute({ type: 'goto', url: 'https://example.com/login' });
  await session.execute({ type: 'fill', selector: "input[name='email']", value: 'user@example.com' });
  await session.execute({ type: 'fill', selector: "input[name='password']", value: 'password' });
  await session.execute({ type: 'click', selector: "button[type='submit']" });

  // Navigate to protected page
  await session.execute({ type: 'goto', url: 'https://example.com/dashboard' });

  // Scrape the page
  const content = await session.scrape();
});
