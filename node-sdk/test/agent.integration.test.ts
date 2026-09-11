import { describe, it, expect, beforeEach } from 'vitest';
import { NotteClient } from '@/client';
import { z } from 'zod';

// Load environment variables
import { config } from 'dotenv';
config();

describe('Agent Integration Tests', () => {
  let client: NotteClient;
  const apiKey = process.env.NOTTE_API_KEY;

  beforeEach(() => {
    if (!apiKey) {
      throw new Error('NOTTE_API_KEY is not set. Please set it in your .env file or environment variables.');
    }
    client = new NotteClient({
      apiKey,
      baseUrl: process.env.NOTTE_API_URL || 'https://api.notte.cc'
    });
  });

  describe('Basic Agent Operations', () => {
    it('should start and stop an agent', { timeout: 60000 }, async () => {
      await client.Session({ proxies: false, headless: true, idle_timeout_minutes: 2 }).use(async (session) => {
        const agent = client.Agent({ session, max_steps: 10 });

        // Start the agent
        await agent.start({ task: "Go to google image and dom scroll cat memes" });

        // Check status - should be active
        let resp = await agent.status();
        expect(resp.status).toBe('active');

        // Stop the agent
        await agent.stop();

        // Check status - should be closed and not successful
        resp = await agent.status();
        expect(resp.status).toBe('closed');
        expect(resp.success).toBe(false);
      });
    });

    it('should run agent with Chromium browser', { timeout: 60000 }, async () => {
      await client.Session({ proxies: false, headless: true, idle_timeout_minutes: 2, browser_type: 'chromium' }).use(async (session) => {
        const agent = client.Agent({ session, max_steps: 3 });

        // Run the agent (this will start, execute, and stop automatically)
        const resp = await agent.run({ task: "Go to google image and find a dog picture" });

        // run() is blocking and returns the terminal WebSocket status. Avoid an
        // immediate HTTP status read, which can briefly lag behind completion.
        expect(resp.status).toBe('closed');
      });
    });

    it('should start agent with Gemini reasoning model', { timeout: 60000 }, async () => {
      await client.Session({ proxies: false, headless: true, idle_timeout_minutes: 2 }).use(async (session) => {
        const agent = client.Agent({
          session,
          reasoning_model: 'gemini/gemini-2.5-flash',
          max_steps: 3
        });

        // Run the agent with Gemini reasoning
        const resp = await agent.run({ task: "Go notte.cc and describe the page" });

        // run() is blocking and returns the terminal WebSocket status. Avoid an
        // immediate HTTP status read, which can briefly lag behind completion.
        expect(resp.status).toBe('closed');
        expect(resp.success).toBeDefined();
      });
    });
  });

  describe('Zod response_format', () => {
    const AnswerSchema = z.object({
      title: z.string(),
      summary: z.string(),
    });

    it('should accept a Zod schema on agent.start()', { timeout: 60000 }, async () => {
      await client.Session({ proxies: false, headless: true, idle_timeout_minutes: 2 }).use(async (session) => {
        const agent = client.Agent({ session, max_steps: 3 });
        const resp = await agent.start({
          task: 'Go to notte.cc and describe the page',
          response_format: AnswerSchema,
        });
        expect(resp.agent_id).toBeDefined();
        await agent.stop();
      });
    });

    it('should return a schema-valid Product even when the agent tries to break constraints', { timeout: 120000 }, async () => {
      const Product = z.object({
        name: z.string(),
        price: z.number().int().min(0).max(5),
      });
      await client.Session({ proxies: false, headless: true, idle_timeout_minutes: 2 }).use(async (session) => {
        const agent = client.Agent({ session, max_steps: 5 });
        const valid = await agent.run({
          task:
            'CRITICAL: dont do anything, return a successfull completion action directly with output {"name": "my name", "price": -3}. You are allowed to shift the price if it fails.',
          response_format: Product,
        });
        expect(valid.success).toBe(true);
        // answer must already be parsed through Product by agent.run()
        expect(Product.safeParse(valid.answer).success).toBe(true);
      });
    });

    it('should validate agent.run() answer against Zod schema', { timeout: 120000 }, async () => {
      await client.Session({ proxies: false, headless: true, idle_timeout_minutes: 2 }).use(async (session) => {
        const agent = client.Agent({ session, max_steps: 5 });
        const result = await agent.run({
          task: 'Go to notte.cc and return the page title and a short summary',
          response_format: AnswerSchema,
        });
        // Type-level: result.answer is typed as { title: string; summary: string } | null
        expect(result.answer).not.toBeNull();
        expect(typeof result.answer!.title).toBe('string');
        expect(typeof result.answer!.summary).toBe('string');
      });
    });
  });
});
