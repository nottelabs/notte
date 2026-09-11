// @sniptest filename=error_handling_2.ts
// @sniptest show=7-25
import { NotteClient } from 'notte-sdk';

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
    const page = await session.page();
    await page.goto('https://example.com');
    throw expectedError;
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
