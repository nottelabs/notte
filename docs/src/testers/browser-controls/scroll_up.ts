// @sniptest filename=scroll_up.ts
// @sniptest show=1-10
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session();
await session.use(async () => {
  await session.execute({ type: "goto", url: "https://en.wikipedia.org/wiki/Web_browser" });
  await session.execute({ type: "scroll_down" });
  await session.execute({ type: "scroll_up" });
});

const status = await session.status();

export { status };
