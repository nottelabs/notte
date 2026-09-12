// @sniptest filename=goto.ts
// @sniptest show=1-8
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session();
await session.use(async () => {
  await session.execute({ type: "goto", url: "https://example.com" });
});

const status = await session.status();

export { status };
