// @sniptest filename=simple_scrape.ts
// @sniptest show=1-7
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const markdown = await client.scrape('https://www.notte.cc', {
  only_main_content: true,
});
console.log(markdown);

export const results = [typeof markdown === 'string', markdown.toLowerCase().includes('notte')];
