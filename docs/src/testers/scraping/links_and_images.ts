// @sniptest filename=links_and_images.ts
// @sniptest show=6-10
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const url = 'https://example.com';

// Include links (default)
let markdown = await client.scrape(url, { scrape_links: true });

// Exclude links
markdown = await client.scrape(url, { scrape_links: false });

// Preserve the displayed overwrite pattern; retain separate responses for option checks.
const withLinks = await client.scrape(url, { scrape_links: true });
const withoutLinks = await client.scrape(url, { scrape_links: false });
export const results = [
  typeof markdown === 'string',
  markdown.includes('Example Domain'),
  withLinks.includes('[Learn more](https://iana.org/help/example-domains)'),
  withoutLinks.includes('Learn more') && !withoutLinks.includes('iana.org'),
];
