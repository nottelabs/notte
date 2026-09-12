// @sniptest filename=ensure_requirements.ts
// @sniptest show=1-11
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session({
  solve_captchas: true, // Must be enabled
  proxies: true, // Helps with detection
});
await session.use(async () => {
  // Use your session here
});

const status = await session.status();
if (status.proxies !== true) throw new Error('Session proxies mismatch');

export { status };
