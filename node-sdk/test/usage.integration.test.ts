import { beforeAll, describe, expect, it } from 'vitest';
import { NotteClient } from '@/client';
import { NotteUsage } from '@/usage';
import { config } from 'dotenv';

config();

describe('Usage Integration Tests', () => {
  let usage: NotteUsage;

  beforeAll(() => {
    const apiKey = process.env.NOTTE_API_KEY;
    if (!apiKey) {
      throw new Error('NOTTE_API_KEY environment variable is required for integration tests');
    }
    const client = new NotteClient({ apiKey, baseUrl: process.env.NOTTE_API_URL || 'https://api.notte.cc' });
    usage = new NotteUsage(client);
  });

  it('get() returns the usage summary shape', async () => {
    const summary = await usage.get();

    expect(typeof summary.plan_type).toBe('string');
    expect(typeof summary.period).toBe('string');
    expect(typeof summary.session_count).toBe('number');
    expect(typeof summary.function_count).toBe('number');
    expect(typeof summary.total_cost).toBe('number');
    expect(typeof summary.balance_amount).toBe('number');
    expect(typeof summary.is_usage_limit_exceeded).toBe('boolean');
  });

  it('logs() returns a paginated page of usage logs', async () => {
    const page = await usage.logs({ page: 1, page_size: 5 });

    expect(Array.isArray(page.items)).toBe(true);
    expect(page.items.length).toBeLessThanOrEqual(5);
    expect(page.page).toBe(1);
    // The API echoes the effective page size, which is 0 when the page is empty.
    expect(typeof page.page_size).toBe('number');
    expect(typeof page.has_next).toBe('boolean');
    expect(typeof page.has_previous).toBe('boolean');
    for (const log of page.items) {
      expect(typeof log.created_at).toBe('string');
      expect(typeof log.endpoint).toBe('string');
      expect(typeof log.duration_ms).toBe('number');
    }
  });
});
