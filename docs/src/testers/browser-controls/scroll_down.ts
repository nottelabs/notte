// @sniptest filename=scroll_down.ts
// @sniptest show=1-9
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const session = client.Session();
await session.use(async () => {
  await session.execute({ type: "goto", url: "https://en.wikipedia.org/wiki/Web_browser" });
  await session.execute({ type: "scroll_down" });
});

const status = await session.status();

export { status };
