import { z } from 'zod';
import { NotteClient } from 'notte-sdk';

const Product = z.object({
  name: z.string(),
  price: z.number(),
});

const client = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY,
});

const url = 'https://example.com/product';
const product = await client.scrape(url, {
  response_format: Product,
});

// Access the extracted data
console.log(`Name: ${product.name}, Price: ${product.price}`);
