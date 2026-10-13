// @sniptest filename=create_session.ts
// @sniptest show=7-20
import { NotteClient, type SessionResponse } from 'notte-sdk';

const client = new NotteClient();
let status: SessionResponse | undefined;
let title: string | undefined;

// Recommended: Use .use() for automatic cleanup.
await client
  .Session({ viewport_width: 1920, viewport_height: 1080 })
  .use(async (session) => {
    console.log(`Session ${session.getId()} is active`);

    // Access the session’s Playwright page.
    status = await session.status();
    const page = await session.page();
    await page.goto('https://example.com');
    title = await page.title();
    console.log(`Page title: ${title}`);
  });
// Automatically stopped here.

export { status, title };
