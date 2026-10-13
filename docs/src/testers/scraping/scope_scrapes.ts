import { NotteClient } from 'notte-sdk';

const client = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY,
});

await client.Session().use(async (session) => {
  // Scrape only the main article, not comments or sidebar
  const content = await session.scrape({
    selector: 'article.main',
  });
});
