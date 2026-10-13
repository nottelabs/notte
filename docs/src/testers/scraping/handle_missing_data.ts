import { z } from 'zod';

const Product = z.object({
  name: z.string(),
  price: z.number(),
  discount_price: z.number().nullable().optional(), // Optional
  rating: z.number().nullable().optional(), // Optional
});
