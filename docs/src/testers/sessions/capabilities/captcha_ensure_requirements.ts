// @sniptest filename=captcha_ensure_requirements.ts
// @sniptest show=1-11
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session({
  solve_captchas: true,
  proxies: true,
});
await session.use(async () => {
  // Use your session here
});

const status = await session.status();
if (status.proxies !== true) throw new Error('Session proxies mismatch');

export { status };
