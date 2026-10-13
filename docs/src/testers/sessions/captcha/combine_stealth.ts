// @sniptest filename=combine_stealth.ts
// @sniptest show=1-13
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session({
  solve_captchas: true,
  proxies: true,
  viewport_width: 1920,
  viewport_height: 1080,
});
await session.use(async () => {
  // Maximum captcha success rate
});

const status = await session.status();
if (status.proxies !== true) throw new Error('Session proxies mismatch');
if (status.viewport_width !== 1920) throw new Error('Session viewport_width mismatch');
if (status.viewport_height !== 1080) throw new Error('Session viewport_height mismatch');

export { status };
