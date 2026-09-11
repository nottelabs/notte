import { beforeAll, describe, expect, it } from 'vitest';
import { NotteClient } from '@/client';
import { NotteSearch } from '@/search';
import { config } from 'dotenv';

config();

describe('Search Integration Tests', () => {
  let search: NotteSearch;

  beforeAll(() => {
    const apiKey = process.env.NOTTE_API_KEY;
    if (!apiKey) {
      throw new Error('NOTTE_API_KEY environment variable is required for integration tests');
    }
    const client = new NotteClient({ apiKey, baseUrl: process.env.NOTTE_API_URL || 'https://api.notte.cc' });
    search = new NotteSearch(client);
  });

  it('returns ranked results for a simple query', async () => {
    const response = await search.search('notte browser automation', { depth: 'fast' });

    expect(response).toBeTypeOf('object');
    expect(Array.isArray(response.results)).toBe(true);
    expect(response.results.length).toBeGreaterThan(0);
    for (const item of response.results) {
      expect(typeof item.url).toBe('string');
      expect(item.url).toMatch(/^https?:\/\//);
      expect(typeof item.name).toBe('string');
    }
  });
});
