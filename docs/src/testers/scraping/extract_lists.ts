import { z } from 'zod';
import { NotteClient } from 'notte-sdk';

const Article = z.object({
  title: z.string(),
  url: z.string(),
  summary: z.string(),
});

const ArticleList = z.object({
  articles: z.array(Article),
});

const client = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY,
});

const articles = await client.scrape('https://news.example.com', {
  response_format: ArticleList,
  instructions: 'Extract all articles from the homepage',
});

for (const article of articles.articles) {
  console.log(`${article.title}: ${article.url}`);
}
