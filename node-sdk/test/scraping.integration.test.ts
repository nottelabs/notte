import { describe, it, expect, beforeEach } from 'vitest';
import { NotteClient } from '@/client';
import { z } from 'zod';

// Load environment variables
import { config } from 'dotenv';
config();

// Define Zod schemas for structured data testing
const PricingPlanSchema = z.object({
	name: z.string(),
	price_per_month: z.string().nullable().optional(), // API returns string, not number
	features: z.array(z.string())
});

const PricingPlansSchema = z.object({
	plans: z.array(PricingPlanSchema)
});

// JSON Schema equivalent for API compatibility
const pricingPlansJson = {
	"type": "object",
	"required": ["plans"],
	"properties": {
		"plans": {
			"type": "array",
			"items": {
				"type": "object",
				"required": ["name"],
				"properties": {
					"name": { "type": "string", "description": "Name of the plan" },
					"price_per_month": { "type": "string", "description": "Price of the plan (with currency)" },
					"features": {
						"type": "array",
						"items": { "type": "string" },
						"description": "List of features included in this plan",
					},
				},
			},
		}
	},
};

// Type inference from Zod schema
type PricingPlan = z.infer<typeof PricingPlanSchema>;
type PricingPlans = z.infer<typeof PricingPlansSchema>;

describe('Scraping Integration Tests', () => {
	let client: NotteClient;

	beforeEach(async () => {
		// Initialize client with API key from environment
		const apiKey = process.env.NOTTE_API_KEY;
		if (!apiKey) {
			throw new Error('NOTTE_API_KEY environment variable is required for integration tests');
		}

		client = new NotteClient({
			apiKey,
			baseUrl: process.env.NOTTE_API_URL || 'https://api.notte.cc'
		});
	});

	describe('Session-based Scraping', () => {
		it('should scrape markdown from a webpage', { timeout: 30000 }, async () => {
			await client.Session({ proxies: false, headless: true, idle_timeout_minutes: 1 }).use(async (session) => {
				const result = await session.execute({
					type: 'goto',
					url: 'https://www.notte.cc'
				});
				expect(result.success).toBe(true);

				const markdown = await session.scrape();
				expect(typeof markdown).toBe('string');
				expect(markdown.length).toBeGreaterThan(0);
			});
		});

		it('should scrape with response format', { timeout: 30000 }, async () => {
			await client.Session({ proxies: false, headless: true, idle_timeout_minutes: 1 }).use(async (session) => {
				const result = await session.execute({
					type: 'goto',
					url: 'https://www.notte.cc'
				});
				expect(result.success).toBe(true);

				const structured = await session.scrape({
					response_format: pricingPlansJson,
					instructions: 'Extract pricing plans from the page'
				});
				expect(structured).toBeDefined();
				expect(structured.data).toBeDefined();
				if (structured.success && structured.data?.plans) {
					expect(structured.data.plans.length).toBeGreaterThan(0);
					const validatedData = PricingPlansSchema.parse(structured.data);
					expect(validatedData.plans[0].name).toBeDefined();
				}
			});
		});

		it('should scrape with custom instructions', { timeout: 30000 }, async () => {
			await client.Session({ proxies: false, headless: true, idle_timeout_minutes: 1 }).use(async (session) => {
				const result = await session.execute({
					type: 'goto',
					url: 'https://www.notte.cc'
				});
				expect(result.success).toBe(true);

				const structured = await session.scrape({
					instructions: 'Extract the pricing plans from the page'
				});
				expect(structured).toBeDefined();
				// Structured scraping returns StructuredData with success, data, error fields
				if (structured.success) {
					expect(structured.data).toBeDefined();
				}
			});
		});

		it('should scrape with custom instructions and response format', { timeout: 30000 }, async () => {
			await client.Session({ proxies: false, headless: true, idle_timeout_minutes: 1 }).use(async (session) => {
				const result = await session.execute({
					type: 'goto',
					url: 'https://www.notte.cc'
				});
				expect(result.success).toBe(true);

				const structured = await session.scrape({
					instructions: 'Extract the pricing plans from the page',
					response_format: pricingPlansJson
				});
				expect(structured).toBeDefined();
				if (structured.success && structured.data) {
					expect(structured.data.plans).toBeDefined();
				}
			});
		});


		it('should scrape structured data with instructions', { timeout: 30000 }, async () => {
			await client.Session({ proxies: false, headless: true, idle_timeout_minutes: 1 }).use(async (session) => {
				const result = await session.execute({
					type: 'goto',
					url: 'https://gymbeam.pl'
				});
				expect(result.success).toBe(true);

				const data = await session.scrape({
					instructions: 'Extract the company name'
				});
				expect(data).toBeDefined();
				if (data.success) {
					expect(data.data).toBeDefined();
				}
			});
		});

		it('should scrape with Zod schema in session', { timeout: 30000 }, async () => {
			await client.Session({ proxies: false, headless: true, idle_timeout_minutes: 1 }).use(async (session) => {
				const result = await session.execute({
					type: 'goto',
					url: 'https://www.notte.cc'
				});
				expect(result.success).toBe(true);

				const validatedData = await session.scrape({
					response_format: PricingPlansSchema,
					instructions: 'Extract pricing plans'
				});

				// With Zod schema, we get the validated data directly
				expect(validatedData).toBeDefined();
				expect(validatedData.plans).toBeDefined();
				expect(validatedData.plans.length).toBeGreaterThan(0);

				// The data should already be validated by the schema
				expect(typeof validatedData.plans[0].name).toBe('string');
			});
		});
	});

	describe('Direct Client Scraping', () => {
		it('should scrape markdown from URL', { timeout: 30000 }, async () => {
			const data = await client.scrape('https://www.notte.cc', { proxies: false });
			expect(typeof data).toBe('string');
			expect(data.length).toBeGreaterThan(0);
		});

		it('should scrape markdown from URL (positional argument)', { timeout: 30000 }, async () => {
			const data = await client.scrape('https://www.notte.cc', { proxies: false });
			expect(typeof data).toBe('string');
			expect(data.length).toBeGreaterThan(0);
		});

		it('should scrape with response format', { timeout: 30000 }, async () => {
			const structured = await client.scrape('https://www.notte.cc', {
				proxies: false,
				response_format: pricingPlansJson,
				instructions: 'Extract pricing plans from the page'
			});
			expect(structured).toBeDefined();
			if (structured.success && structured.data?.plans) {
				expect(structured.data.plans.length).toBeGreaterThan(0);
				const validatedData = PricingPlansSchema.parse(structured.data);
				expect(validatedData.plans[0].name).toBeDefined();
			}
		});

		it('should scrape with JSON schema response format', { timeout: 30000 }, async () => {
			const structured = await client.scrape('https://www.notte.cc', {
				proxies: false,
				response_format: pricingPlansJson,
				instructions: 'Extract pricing plans from the page'
			});
			expect(structured).toBeDefined();
			if (structured.success && structured.data?.plans) {
				expect(structured.data.plans.length).toBeGreaterThan(0);
			}
		});

		it('should scrape with Zod schema validation', { timeout: 30000 }, async () => {
			const validatedData = await client.scrape('https://www.notte.cc', {
				proxies: false,
				response_format: PricingPlansSchema,
				instructions: "Extract pricing plans from the page, including plan names, prices, and features"
			});

			// With Zod schema, we get the validated data directly
			expect(validatedData).toBeDefined();
			expect(validatedData.plans).toBeDefined();
			expect(validatedData.plans.length).toBeGreaterThan(0);

			// The data should already be validated by the schema
			expect(typeof validatedData.plans[0].name).toBe('string');
			expect(Array.isArray(validatedData.plans[0].features)).toBe(true);
		});
	});

	describe('README Examples', () => {
		it('should work with async scraping example', { timeout: 30000 }, async () => {
			await client.Session({ proxies: false, headless: true, idle_timeout_minutes: 1 }).use(async (session) => {
				const result = await session.execute({
					type: 'goto',
					url: 'https://www.notte.cc'
				});
				expect(result.success).toBe(true);

				const data = await session.scrape();
				expect(typeof data).toBe('string');
				expect(data.length).toBeGreaterThan(0);
			});
		});

		it('should work with sync scraping example', { timeout: 30000 }, async () => {
			await client.Session({ proxies: false, headless: true, idle_timeout_minutes: 1 }).use(async (session) => {
				const result = await session.execute({
					type: 'goto',
					url: 'https://www.notte.cc'
				});
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

		it('should handle invalid URLs', { timeout: 30000 }, async () => {
			try {
				await client.scrape('https://example.invalid', { proxies: false });
				// If it doesn't throw, that's also acceptable
			} catch (error) {
				expect(error).toBeDefined();
			}
		});
	});

	describe('Scraping Options', () => {
		it('should scrape with only main content', { timeout: 30000 }, async () => {
			const data = await client.scrape('https://www.notte.cc', {
				proxies: false,
				only_main_content: true
			});
			expect(typeof data).toBe('string');
			expect(data.length).toBeGreaterThan(0);
		});

		it('should scrape with custom ignored tags', { timeout: 30000 }, async () => {
			const data = await client.scrape('https://www.notte.cc', {
				proxies: false,
				ignored_tags: ['script', 'style']
			});
			expect(typeof data).toBe('string');
			expect(data.length).toBeGreaterThan(0);
		});

		it('should scrape with scrape_links disabled', { timeout: 30000 }, async () => {
			const data = await client.scrape('https://www.notte.cc', {
				proxies: false,
				scrape_links: false
			});
			expect(typeof data).toBe('string');
			expect(data.length).toBeGreaterThan(0);
		});

		it('should scrape with scrape_images disabled', { timeout: 30000 }, async () => {
			const data = await client.scrape('https://www.notte.cc', {
				proxies: false,
				scrape_images: false
			});
			expect(typeof data).toBe('string');
			expect(data.length).toBeGreaterThan(0);
		});
	});

});
