// @sniptest filename=wait.ts
// @sniptest show=1-14
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session();
await session.use(async () => {
  await session.execute({ type: "goto", url: "https://example.com" });

  // Wait 2 seconds
  await session.execute({ type: "wait", time_ms: 2000 });

  // Wait 5 seconds for page to load
  await session.execute({ type: "wait", time_ms: 5000 });
});

const status = await session.status();

export { status };
