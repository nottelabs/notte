// @sniptest filename=wait_time.ts
// @sniptest show=1-10
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session();
await session.use(async () => {

  // Wait 2 seconds
  await session.execute({ type: "wait", time_ms: 2000 });
});

const status = await session.status();

export { status };
