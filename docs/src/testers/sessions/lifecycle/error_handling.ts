// @sniptest filename=error_handling.ts
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';

const client = new NotteClient();
const session = client.Session({ idle_timeout_minutes: 2 });
const expectedError = new Error('Example automation failure');
let sessionId: string | null = null;

try {
  await session.use(async () => {
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
  });
} catch (error) {
  if (error !== expectedError) throw error;
  console.log(
    JSON.stringify({ session_id: sessionId, error: expectedError.message }),
  );
}
// Cleanup happens even when automation throws.
