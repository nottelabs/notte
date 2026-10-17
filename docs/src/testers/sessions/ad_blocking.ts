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

const statuses = await Promise.all([defaultSession.status(), session.status()]);
const results = statuses.map(status => status.status);
const session_ids = statuses.map(status => status.session_id);
export { results, session, session_ids };
