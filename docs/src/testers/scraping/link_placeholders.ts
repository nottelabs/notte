// @sniptest filename=link_placeholders.ts
// @sniptest show=6-9
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const url = 'https://example.com';

// Use placeholders for links and images
const markdown = await client.scrape(url, {
  use_link_placeholders: true,
});

export const results = [
  typeof markdown === 'string',
  markdown.includes('Example Domain'),
  markdown.includes('[Learn more](link1)'),
  !markdown.includes('iana.org'),
];
