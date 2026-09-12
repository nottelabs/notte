// @sniptest filename=combine_techniques.ts
// @sniptest show=1-14
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session({
  browser_type: "chrome",
  proxies: true,
  viewport_width: 1920,
  viewport_height: 1080,
  user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
});
await session.use(async () => {
  // Maximum stealth configuration
});

const status = await session.status();
if (status.browser_type !== "chrome") throw new Error('Session browser_type mismatch');
if (status.proxies !== true) throw new Error('Session proxies mismatch');
if (status.viewport_width !== 1920) throw new Error('Session viewport_width mismatch');
if (status.viewport_height !== 1080) throw new Error('Session viewport_height mismatch');
if (status.user_agent !== "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36") throw new Error('Session user_agent mismatch');

export { status };
