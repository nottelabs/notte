// @sniptest filename=selenium_playwright_alternative.ts
// @sniptest show=1-18
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';

const client = new NotteClient();

const status = await client.Session().use(async session => {
  const status = await session.status();
  const browser = await chromium.connectOverCDP(status.cdp_url!);
  try {
    const page = browser.contexts()[0].pages()[0];
    // Use Playwright for automation
    await page.goto('https://example.com');
    console.log(`Title: ${await page.title()}`);
  } finally {
    await browser.close();
  }
  return status;
});

export { status };
