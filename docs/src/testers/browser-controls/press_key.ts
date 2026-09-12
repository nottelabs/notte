// @sniptest filename=press_key.ts
// @sniptest show=1-17
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session();
await session.use(async () => {
  await session.execute({ type: "goto", url: "https://example.com" });

  // Press Enter
  await session.execute({ type: "press_key", key: "Enter" });

  // Press Escape
  await session.execute({ type: "press_key", key: "Escape" });

  // Press Tab
  await session.execute({ type: "press_key", key: "Tab" });
});

const status = await session.status();

export { status };
