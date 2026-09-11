// @sniptest filename=create_session_2.ts
// @sniptest show=8-26
import { NotteClient, type SessionResponse } from 'notte-sdk';
import { chromium } from 'playwright-core';

const client = new NotteClient();
let status: SessionResponse | undefined;
let title: string | undefined;

const session = client.Session();
await session.start();
try {
  console.log(`Session ${session.getId()} is active`);
  status = await session.status();
  if (status.status !== 'active') throw new Error('Session is not active');
  if (!status.cdp_url) throw new Error('Session did not return a CDP URL');
  const browser = await chromium.connectOverCDP(status.cdp_url);
  try {
    const page = browser.contexts()[0].pages()[0];
    await page.goto('https://example.com');
    title = await page.title();
  } finally {
    await browser.close();
  }
} finally {
  // Always stop the session
  await session.stop();
}

export { status, title };
