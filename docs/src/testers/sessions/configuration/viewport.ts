// @sniptest filename=viewport.ts
// @sniptest show=8-25
import { NotteClient, type SessionResponse } from 'notte-sdk';

const client = new NotteClient();
let status: SessionResponse | undefined;
let title: string | undefined;
let viewport: { width: number; height: number } | undefined;

const session = client.Session({
  viewport_width: 3840,
  viewport_height: 2160,
});
await session.use(async () => {
  status = await session.status();
  if (status.status !== 'active') throw new Error('Session is not active');
  const page = await session.page();
  await page.goto('https://example.com');
  title = await page.title();
  console.log(`Page title: ${title}`);
  viewport = await page.evaluate(() => ({
    width: window.innerWidth,
    height: window.innerHeight,
  }));
  console.log(viewport);
});
// Automatically stopped here.

export { status, title, viewport };
