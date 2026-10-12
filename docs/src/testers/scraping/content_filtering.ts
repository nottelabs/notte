// @sniptest filename=content_filtering.ts
// @sniptest show=6-10
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const url = 'https://example.com';

// Include all page content (default)
let markdown = await client.scrape(url, { only_main_content: false });

// Only main content (excludes navbars, footers, sidebars)
markdown = await client.scrape(url, { only_main_content: true });

export const results = [typeof markdown === 'string', markdown.includes('Example Domain')];
