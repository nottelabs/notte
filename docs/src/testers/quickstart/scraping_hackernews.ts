import { z } from 'zod';
import { NotteClient } from 'notte-sdk';

const HackerNewsPost = z.object({
  title: z.string(),
  url: z.string(),
  points: z.number(),
  author: z.string(),
});

const HackerNewsFeed = z.object({
  posts: z.array(HackerNewsPost),
});

const notte = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY,
});

const result = await notte.scrape('https://news.ycombinator.com', {
  instructions: 'Extract the top 5 posts from the front page',
  response_format: HackerNewsFeed,
});

result.posts.forEach((post, index) => {
  console.log(`${index + 1}. ${post.points} - ${post.title}`);
});
