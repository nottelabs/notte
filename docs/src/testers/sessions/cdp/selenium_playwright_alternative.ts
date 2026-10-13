// @sniptest filename=selenium_playwright_alternative.ts
// @sniptest show=1-12
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const status = await client.Session().use(async session => {
  const status = await session.status();
  const page = await session.page();
  // Use Playwright for automation
  await page.goto('https://example.com');
  console.log(`Title: ${await page.title()}`);
  return status;
});

export { status };
