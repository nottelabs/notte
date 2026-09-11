// @sniptest filename=proxies_simple.ts
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';

const client = new NotteClient();

await client
  .Session({ idle_timeout_minutes: 2, proxies: true })
  .use(async (session) => {
    const status = await session.status();
    if (status.status !== 'active') throw new Error('Session is not active');
    const cdpUrl = status.cdp_url;
    if (!cdpUrl) throw new Error('Session did not return a CDP URL');
    const browser = await chromium.connectOverCDP(cdpUrl);
    try {
      const page = browser.contexts()[0].pages()[0];
      await page.goto('https://example.com');
      console.log(
        JSON.stringify({
          session_id: session.getId(),
          status: status.status,
          idle_timeout_minutes: status.idle_timeout_minutes,
          title: await page.title(),
        }),
      );
    } finally {
      await browser.close();
    }
  });
// Automatically stopped here.
