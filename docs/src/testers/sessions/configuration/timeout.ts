// @sniptest filename=timeout.ts
// @sniptest show=8-23
import { NotteClient, type SessionResponse } from 'notte-sdk';
import { chromium } from 'playwright-core';

const client = new NotteClient();
let status: SessionResponse | undefined;
let title: string | undefined;

const session = client.Session({ idle_timeout_minutes: 10 });
await session.use(async () => {
  status = await session.status();
  if (status.status !== 'active') throw new Error('Session is not active');
  if (!status.cdp_url) throw new Error('Session did not return a CDP URL');
  const browser = await chromium.connectOverCDP(status.cdp_url);
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
