// @sniptest filename=error_handling_2.ts
// @sniptest show=8-32
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';

const client = new NotteClient();
let sessionId: string | null = null;
let errorMessage: string | undefined;

const session = client.Session();
const expectedError = new Error('Example automation failure');
try {
  await session.start();
  try {
    sessionId = session.getId();
    const status = await session.status();
    if (!status.cdp_url) throw new Error('Session did not return a CDP URL');
    const browser = await chromium.connectOverCDP(status.cdp_url);
    try {
      const page = browser.contexts()[0].pages()[0];
      await page.goto('https://example.com');
      throw expectedError;
    } finally {
      await browser.close();
    }
  } finally {
    await session.stop();
  }
} catch (error) {
  if (error !== expectedError) throw error;
  errorMessage = expectedError.message;
  console.log(`Automation failed: ${errorMessage}`);
}
// Cleanup happens even when automation throws.

export { sessionId as session_id, errorMessage as error_message };
