// @sniptest filename=quickstart.ts
// @sniptest show=1-5
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const markdown = await client.scrape('https://example.com');
console.log(markdown);

export const results = [typeof markdown === 'string', markdown.includes('Example Domain')];
