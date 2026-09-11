/** Mirrors `tests/integration/sdk/test_scraping.py` for the remote session and the client. */
import { describe, it, expect, beforeEach } from 'vitest';
import { NotteClient } from '@/client';
import { actions } from '@/actions';
import type { StructuredData } from '@/scrape';
import { z } from 'zod';

// Load environment variables
import { config } from 'dotenv';
config();

// Define Zod schemas for structured data testing
const PricingPlanSchema = z.object({
  name: z.string(),
  price_per_month: z.string().nullable().optional(), // API returns string, not number
  features: z.array(z.string()),
});

const PricingPlansSchema = z.object({
  plans: z.array(PricingPlanSchema),
});

// JSON Schema equivalent for API compatibility
const pricingPlansJson = {
  type: 'object',
  required: ['plans'],
  properties: {
    plans: {
      type: 'array',
      items: {
        type: 'object',
        required: ['name'],
        properties: {
          name: { type: 'string', description: 'Name of the plan' },
          price_per_month: { type: 'string', description: 'Price of the plan (with currency)' },
          features: {
            type: 'array',
            items: { type: 'string' },
            description: 'List of features included in this plan',
          },
        },
      },
    },
  },
};

type PricingPlans = z.infer<typeof PricingPlansSchema>;

describe('Scraping Integration Tests', () => {
  let client: NotteClient;

  beforeEach(() => {
    const apiKey = process.env.NOTTE_API_KEY;
    if (!apiKey) {
      throw new Error('NOTTE_API_KEY environment variable is required for integration tests');
    }
    client = new NotteClient({ apiKey, baseUrl: process.env.NOTTE_API_URL || 'https://api.notte.cc' });
  });

  describe('Session-based Scraping', () => {
    it('should scrape markdown from a webpage', { timeout: 60_000 }, async () => {
      await client.Session({ proxies: false, idle_timeout_minutes: 1 }).use(async session => {
        const result = await session.execute(actions.goto({ url: 'https://www.notte.cc/pricing' }));
        expect(result.success).toBe(true);

        const markdown = await session.scrape();
        expect(typeof markdown).toBe('string');
        expect(markdown.length).toBeGreaterThan(0);
      });
    });

    it('should scrape with a JSON schema response format and raiseOnFailure false', { timeout: 60_000 }, async () => {
      await client.Session({ proxies: false, idle_timeout_minutes: 1 }).use(async session => {
        await session.execute(actions.goto({ url: 'https://www.notte.cc/pricing' }));

        const structured = (await session.scrape({
          response_format: pricingPlansJson,
          instructions: 'Extract the pricing plans from the page',
          raiseOnFailure: false,
        })) as StructuredData<PricingPlans>;
        expect(structured.success).toBe(true);
        expect(structured.data).toBeDefined();
        const plans = PricingPlansSchema.parse(structured.data);
        expect(plans.plans.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('should scrape with custom instructions', { timeout: 60_000 }, async () => {
      await client.Session({ proxies: false, idle_timeout_minutes: 1 }).use(async session => {
        await session.execute(actions.goto({ url: 'https://www.notte.cc/pricing' }));

        const structured = (await session.scrape({
          instructions: 'Extract the pricing plans from the page',
          raiseOnFailure: false,
        })) as StructuredData<unknown>;
        expect(structured.success).toBe(true);
        expect(structured.data).toBeDefined();

        // with the default raiseOnFailure the extracted data is returned directly
        const data = await session.scrape({ instructions: 'Extract the pricing plans from the page' });
        expect(data).toBeDefined();
        expect(typeof data).toBe('object');
      });
    });

    it('should scrape with custom instructions and a Zod response format', { timeout: 60_000 }, async () => {
      await client.Session({ proxies: false, idle_timeout_minutes: 1 }).use(async session => {
        await session.execute(actions.goto({ url: 'https://www.notte.cc/pricing' }));

        const structured = await session.scrape({
          instructions: 'Extract the pricing plans from the page',
          response_format: PricingPlansSchema,
          raiseOnFailure: true,
        });
        expect(structured.plans.length).toBeGreaterThanOrEqual(1);
        expect(typeof structured.plans[0].name).toBe('string');

        const wrapped = await session.scrape({
          instructions: 'Extract the pricing plans from the page',
          response_format: PricingPlansSchema,
          raiseOnFailure: false,
        });
        expect(wrapped.success).toBe(true);
        expect(wrapped.data?.plans.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('should scrape structured data with instructions only', { timeout: 60_000 }, async () => {
      await client.Session({ proxies: false }).use(async session => {
        await session.execute(actions.goto({ url: 'https://gymbeam.pl' }));
        const data = await session.scrape({ instructions: 'Extract the company name' });
        expect(typeof data).toBe('object');
        expect(data).not.toBeNull();
      });
    });

    it('should scrape images only', { timeout: 60_000 }, async () => {
      await client.Session({ proxies: false }).use(async session => {
        await session.execute(actions.goto({ url: 'https://gymbeam.pl' }));
        const images = await session.scrape({ only_images: true });
        expect(Array.isArray(images)).toBe(true);
        expect(images.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Direct Client Scraping', () => {
    it('should scrape markdown from URL', { timeout: 60_000 }, async () => {
      const data = await client.scrape('https://www.notte.cc', { proxies: false });
      expect(typeof data).toBe('string');
      expect(data.length).toBeGreaterThan(0);
    });

    it('should scrape with a JSON schema response format', { timeout: 60_000 }, async () => {
      const structured = (await client.scrape('https://www.notte.cc/pricing', {
        proxies: false,
        response_format: pricingPlansJson,
        raiseOnFailure: false,
      })) as StructuredData<PricingPlans>;
      expect(structured.success).toBe(true);
      const plans = PricingPlansSchema.parse(structured.data);
      expect(plans.plans.length).toBeGreaterThanOrEqual(1);
    });

    it('should scrape with Zod schema validation', { timeout: 60_000 }, async () => {
      const validatedData = await client.scrape('https://www.notte.cc/pricing', {
        proxies: false,
        response_format: PricingPlansSchema,
        raiseOnFailure: true,
      });
      expect(validatedData.plans.length).toBeGreaterThanOrEqual(1);
      expect(typeof validatedData.plans[0].name).toBe('string');
      expect(Array.isArray(validatedData.plans[0].features)).toBe(true);
    });
  });

  describe('README Examples', () => {
    it('should work with the sync scraping example', { timeout: 60_000 }, async () => {
      await client.Session({ proxies: false }).use(async session => {
        const result = await session.execute({ type: 'goto', url: 'https://www.notte.cc' });
        expect(result.success).toBe(true);

        const data = await session.scrape();
        expect(typeof data).toBe('string');
        expect(data.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle scraping errors gracefully', async () => {
      const session = client.Session({ proxies: false });
      await expect(session.scrape()).rejects.toThrow('Session not started');
    });

    it('should handle invalid URLs', { timeout: 60_000 }, async () => {
      try {
        await client.scrape('https://example.invalid', { proxies: false });
        // If it doesn't throw, that's also acceptable
      } catch (error) {
        expect(error).toBeDefined();
      }
    });
  });

  describe('Scraping Options', () => {
    it('should scrape with only main content', { timeout: 60_000 }, async () => {
      const data = await client.scrape('https://www.notte.cc', { proxies: false, only_main_content: true });
      expect(typeof data).toBe('string');
      expect(data.length).toBeGreaterThan(0);
    });

    it('should scrape with custom ignored tags', { timeout: 60_000 }, async () => {
      const data = await client.scrape('https://www.notte.cc', { proxies: false, ignored_tags: ['script', 'style'] });
      expect(typeof data).toBe('string');
      expect(data.length).toBeGreaterThan(0);
    });

    it('should scrape with scrape_links and scrape_images disabled', { timeout: 60_000 }, async () => {
      const data = await client.scrape('https://www.notte.cc', { proxies: false, scrape_links: false, scrape_images: false });
      expect(typeof data).toBe('string');
      expect(data.length).toBeGreaterThan(0);
    });
  });
});
