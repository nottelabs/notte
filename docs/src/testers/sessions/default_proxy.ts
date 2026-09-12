// @sniptest filename=default_proxy.ts
// @sniptest show=1-11
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session({
  proxies: true,
});
await session.use(async () => {
  await session.execute({ type: 'goto', url: 'https://www.notte.cc/' });
  await session.observe();
});

const status = await session.status();
if (status.proxies !== true) throw new Error('Session proxies mismatch');

export { status };
