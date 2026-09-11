// @sniptest filename=quick_start.ts
// @sniptest show=7-16
import { NotteClient, type SessionResponse } from 'notte-sdk';

const client = new NotteClient();
let status: SessionResponse | undefined;
let title: string | undefined;

const session = client.Session();
await session.use(async () => {
  status = await session.status();
  if (status.status !== 'active') throw new Error('Session is not active');
  const page = await session.page();
  await page.goto('https://example.com');
  title = await page.title();
  console.log(`Page title: ${title}`);
});
// Automatically stopped here.

export { status, title };
