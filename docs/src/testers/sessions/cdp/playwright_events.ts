// @sniptest filename=playwright_events.ts
// @sniptest show=1-28
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';

const client = new NotteClient();

const status = await client.Session().use(async session => {
  const status = await session.status();
  const browser = await chromium.connectOverCDP(status.cdp_url!);
  try {
    const page = browser.contexts()[0].pages()[0];
    // Listen to console messages
    page.on('console', msg => console.log(`Console: ${msg.text()}`));

    // Listen to page errors
    page.on('pageerror', err => console.log(`Error: ${err}`));

    // Listen to requests
    page.on('request', req => console.log(`Request: ${req.url()}`));

    // Listen to responses
    page.on('response', res => console.log(`Response: ${res.url()} - ${res.status()}`));

    await page.goto('https://example.com');
  } finally {
    await browser.close();
  }
  return status;
});

export { status };
