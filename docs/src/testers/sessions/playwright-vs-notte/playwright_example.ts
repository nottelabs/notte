// @sniptest show=1-24
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';

const client = new NotteClient();

const status = await client.Session().use(async session => {
  const status = await session.status();
  const browser = await chromium.connectOverCDP(status.cdp_url!);
  try {
    const page = browser.contexts()[0].pages()[0];

    // Block images for faster loading
    await page.route('**/*.{png,jpg,jpeg}', route => route.abort());

    // Listen to network requests
    page.on('request', req => console.log(`→ ${req.url()}`));
    page.on('response', res => console.log(`← ${res.url()} (${res.status()})`));

    await page.goto('https://example.com');
  } finally {
    await browser.close();
  }
  return status;
});

export { status };
