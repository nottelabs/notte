// @sniptest filename=selenium_javascript.ts
// @sniptest show=1-31
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';

const client = new NotteClient();

const status = await client.Session().use(async session => {
  const status = await session.status();
  const browser = await chromium.connectOverCDP(status.cdp_url!);
  try {
    const page = browser.contexts()[0].pages()[0];
    await page.goto('https://example.com');

    // Execute JavaScript
    let result = await page.evaluate('document.title');
    console.log(`Title: ${result}`);

    // Execute complex script
    const data = await page.evaluate(() => {
      const items = document.querySelectorAll('.item');
      return Array.from(items).map(item => item.textContent);
    });
    console.log(`Items: ${data}`);

    // Pass arguments to JavaScript
    result = await page.evaluate(x => x * 2, 5);
    console.log(`Result: ${result}`); // 10
  } finally {
    await browser.close();
  }
  return status;
});

export { status };
