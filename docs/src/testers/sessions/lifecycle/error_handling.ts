// @sniptest filename=error_handling.ts
// @sniptest show=7-22
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
let sessionId: string | null = null;
let errorMessage: string | undefined;

const session = client.Session();
const expectedError = new Error('Example automation failure');
try {
  await session.use(async () => {
    sessionId = session.getId();
    const status = await session.status();
    const page = await session.page();
    await page.goto('https://example.com');
    throw expectedError;
  });
} catch (error) {
  if (error !== expectedError) throw error;
  errorMessage = expectedError.message;
  console.log(`Automation failed: ${errorMessage}`);
}
// Cleanup happens even when automation throws.

export { sessionId as session_id, errorMessage as error_message };
