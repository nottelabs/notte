import { chromium } from 'playwright-core';
import { NotteClient } from 'notte-sdk';

const notte = new NotteClient();

await notte.Session({ idle_timeout_minutes: 2 }).use(async (session) => {
  const status = await session.status();
  const cdpUrl = status.cdp_url;

  if (!cdpUrl) {
    throw new Error('Session did not return a cdp_url');
  }

  const browser = await chromium.connectOverCDP(cdpUrl);

  try {
    const page = browser.contexts()[0].pages()[0];
    await page.goto('https://www.google.com');
    await page.screenshot({ path: process.env.NOTTE_SCREENSHOT_PATH || 'screenshot.png' });
  } finally {
    await browser.close();
  }
});
