import { z } from 'zod';
import { NotteClient } from 'notte-sdk';

const ResearchPaper = z.object({
  title: z.string(),
  authors: z.array(z.string()),
  abstract: z.string(),
  publication_date: z.string().nullable(),
  citations: z.number().nullable(),
});

const client = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY,
});

const result = await client.scrape('https://papers.example.com/paper/123', {
  response_format: ResearchPaper,
});
