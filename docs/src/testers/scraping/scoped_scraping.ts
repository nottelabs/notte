import { NotteClient } from 'notte-sdk';

const client = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY,
});

await client.Session().use(async (session) => {
  // Scrape content within a specific selector
  const articleContent = await session.scrape({
    selector: 'article.main-content',
  });

  // Scrape a specific container
  const productContent = await session.scrape({
    selector: '#product-details',
  });
});
