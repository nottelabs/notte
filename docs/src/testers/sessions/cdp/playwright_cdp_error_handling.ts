// @sniptest filename=playwright_cdp_error_handling.ts
// @sniptest show=1-20
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';

const client = new NotteClient();

const status = await client.Session().use(async session => {
  const status = await session.status();
  const cdpUrl = status.cdp_url!;
  try {
    const browser = await chromium.connectOverCDP(cdpUrl);
    try {
      // ... operations
      return status;
    } finally {
      await browser.close();
    }
  } catch (error) {
    console.log(`CDP connection failed: ${error}`);
  }
});

export { status };
