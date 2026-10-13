import { z } from 'zod';
import { NotteClient } from 'notte-sdk';

const client = new NotteClient({
  apiKey: process.env.NOTTE_API_KEY,
});

const ContactInfo = z.object({
  email: z.string(),
  phone: z.string().nullable(),
});

await client.Session().use(async (session) => {
  const agent = client.Agent({ session });
  const result = await agent.run({
    task: 'Extract contact information',
    response_format: ContactInfo,
  });
});
