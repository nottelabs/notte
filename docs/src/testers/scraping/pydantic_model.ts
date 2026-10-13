import { z } from 'zod';
import { NotteClient } from 'notte-sdk';

const Product = z.object({
  name: z.string(),
  price: z.number(),
  description: z.string(),
});

const client = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY,
});

const product = await client.scrape('https://example.com/product', {
  response_format: Product,
  instructions: 'Extract the product details',
});

console.log(`Name: ${product.name}, Price: ${product.price}`);
