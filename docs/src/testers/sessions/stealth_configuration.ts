// @sniptest filename=stealth_configuration.ts
// @sniptest show=1-16
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session({
  solve_captchas: true,
  proxies: [{ type: 'notte', country: 'us' }],
  user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  viewport_width: 1920,
  viewport_height: 1080,
});
await session.use(async () => {
  await session.execute({ type: 'goto', url: 'https://example.com' });
  const result = await session.observe();
  console.log('Success with fallback configuration');
});

const status = await session.status();
if (status.proxies !== true) throw new Error('Session proxies mismatch');
if (status.user_agent !== "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36") throw new Error('Session user_agent mismatch');
if (status.viewport_width !== 1920) throw new Error('Session viewport_width mismatch');
if (status.viewport_height !== 1080) throw new Error('Session viewport_height mismatch');

export { status };
