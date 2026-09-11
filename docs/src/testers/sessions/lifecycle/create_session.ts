// @sniptest filename=create_session.ts
// @sniptest show=8-26
import { NotteClient, type SessionResponse } from 'notte-sdk';
import { chromium } from 'playwright-core';

const client = new NotteClient();
let status: SessionResponse | undefined;
let title: string | undefined;

// Recommended: Use .use() for automatic cleanup.
await client
  .Session({ viewport_width: 1920, viewport_height: 1080 })
  .use(async (session) => {
    console.log(`Session ${session.getId()} is active`);

    // Connect Playwright to access the page.
    status = await session.status();
    const browser = await chromium.connectOverCDP(status.cdp_url!);
    try {
      const page = browser.contexts()[0].pages()[0];
      await page.goto('https://example.com');
      title = await page.title();
      console.log(`Page title: ${title}`);
    } finally {
      await browser.close();
    }
  });
// Automatically stopped here.

export { status, title };
