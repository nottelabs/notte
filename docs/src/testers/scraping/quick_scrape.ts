// @sniptest filename=quick_scrape.ts
// @sniptest show=1-6
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

// Returns markdown content
const markdown = await client.scrape('https://example.com');

export const results = [typeof markdown === 'string', markdown.includes('Example Domain')];
