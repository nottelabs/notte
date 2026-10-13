// @sniptest filename=ad_blocking.ts
// @sniptest show=1-15
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

// Ad blocking is on by default
const defaultSession = client.Session();
await defaultSession.use(async (s) => {
  await s.execute({ type: 'goto', url: 'https://example.com' });
});

// Turn it off when a site needs its ads or trackers to load
const session = client.Session({ block_ads: false });
await session.use(async (s) => {
  await s.execute({ type: 'goto', url: 'https://example.com' });
});

const results = [(await defaultSession.status()).status, (await session.status()).status];
export { results, session };
