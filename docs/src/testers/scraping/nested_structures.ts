import { z } from 'zod';
import { NotteClient } from 'notte-sdk';

const Address = z.object({
  street: z.string(),
  city: z.string(),
  country: z.string(),
});

const Company = z.object({
  name: z.string(),
  description: z.string(),
  address: Address,
  employee_count: z.number().nullable(),
});

const client = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY,
});

const company = await client.scrape('https://example.com/about', {
  response_format: Company,
  instructions: 'Extract company information including address',
});

console.log(company.address.city);
