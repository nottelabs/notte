// @sniptest filename=selenium_javascript.ts
// @sniptest show=1-25
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const status = await client.Session().use(async session => {
  const status = await session.status();
  const page = await session.page();
  await page.goto('https://example.com');

  // Execute JavaScript
  let result = await page.evaluate('document.title');
  console.log(`Title: ${result}`);

  // Execute complex script
  const data = await page.evaluate(() => {
    const items = document.querySelectorAll('.item');
    return Array.from(items).map(item => item.textContent);
  });
  console.log('Items:', data);

  // Pass arguments to JavaScript
  result = await page.evaluate(x => x * 2, 5);
  console.log(`Result: ${result}`); // 10
  return status;
});

export { status };
