// @sniptest filename=playwright_timeout.ts
// @sniptest show=1-8
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const status = await client.Session({ idle_timeout_minutes: 20, max_duration_minutes: 20 }).use(async session => {
  // Long Playwright automation
  return session.status();
});

export { status };
