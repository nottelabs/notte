// @sniptest filename=full_config.ts
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';

const client = new NotteClient();

await client
  .Session({
    idle_timeout_minutes: 10,
    advanced_stealth: false,
    solve_captchas: true,
    proxies: true,
    viewport_width: 1920,
    viewport_height: 1080,
    browser_type: 'chromium',
  })
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
          viewport: await page.evaluate(() => ({
            width: window.innerWidth,
            height: window.innerHeight,
          })),
        }),
      );
    } finally {
      await browser.close();
    }
  });
// Automatically stopped here.
