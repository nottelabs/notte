// @sniptest filename=create_session_2.ts
// @sniptest show=7-19
import { NotteClient, type SessionResponse } from 'notte-sdk';

const client = new NotteClient();
let status: SessionResponse | undefined;
let title: string | undefined;

const session = client.Session();
await session.start();
try {
  console.log(`Session ${session.getId()} is active`);
  status = await session.status();
  if (status.status !== 'active') throw new Error('Session is not active');
  const page = await session.page();
  await page.goto('https://example.com');
  title = await page.title();
} finally {
  // Always stop the session
  await session.stop();
}

export { status, title };
