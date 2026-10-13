// @sniptest show=1-18
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const status = await client.Session().use(async session => {
  const status = await session.status();
  const page = await session.page();

  // Block images for faster loading
  await page.route('**/*.{png,jpg,jpeg}', route => route.abort());

  // Listen to network requests
  page.on('request', req => console.log(`→ ${req.url()}`));
  page.on('response', res => console.log(`← ${res.url()} (${res.status()})`));

  await page.goto('https://example.com');
  return status;
});

export { status };
