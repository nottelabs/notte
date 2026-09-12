// @sniptest filename=content_filtering.ts
// @sniptest show=6-10
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const url = 'https://example.com';

// Only main content (excludes navbars, footers, sidebars)
let markdown = await client.scrape(url, { only_main_content: true }); // Default

// Include all page content
markdown = await client.scrape(url, { only_main_content: false });

export const results = [typeof markdown === 'string', markdown.includes('Example Domain')];
