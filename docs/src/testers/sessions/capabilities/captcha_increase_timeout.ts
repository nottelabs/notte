// @sniptest filename=captcha_increase_timeout.ts
// @sniptest show=1-11
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session({
  solve_captchas: true,
  idle_timeout_minutes: 15, // Longer timeout
});
await session.use(async () => {
  // Use your session here
});

const status = await session.status();
if (status.idle_timeout_minutes !== 15) throw new Error('Session idle_timeout_minutes mismatch');

export { status };
