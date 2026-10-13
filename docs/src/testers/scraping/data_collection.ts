import { z } from 'zod';
import { NotteClient } from 'notte-sdk';

const ProductInfo = z.object({
  name: z.string(),
  price: z.number(),
  rating: z.number().nullable(),
  reviews_count: z.number().nullable(),
});

const client = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY,
});

const urls = [
  'https://store.example.com/product/1',
  'https://store.example.com/product/2',
];

const products = [];
for (const url of urls) {
  const data = await client.scrape(url, {
    response_format: ProductInfo,
  });
  products.push(data);
}
