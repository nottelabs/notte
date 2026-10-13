import { z } from 'zod';

// Good - matches page structure
const GoodProduct = z.object({
  name: z.string(),
  price: z.number(),
  in_stock: z.boolean(),
});

// Bad - fields that may not exist
const BadProduct = z.object({
  name: z.string(),
  price: z.number(),
  manufacturer: z.string(), // Page might not have this
  warranty: z.string(), // Page might not have this
});
