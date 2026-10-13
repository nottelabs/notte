// @sniptest filename=reload.ts
// @sniptest show=1-9
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session();
await session.use(async () => {
  await session.execute({ type: "goto", url: "https://example.com" });
  await session.execute({ type: "reload" });
});

const status = await session.status();

export { status };
