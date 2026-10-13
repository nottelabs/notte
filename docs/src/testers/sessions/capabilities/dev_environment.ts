// @sniptest filename=dev_environment.ts
// @sniptest show=1-11
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

// Only use live view in development
const isDev = process.env.ENV === 'development';

const session = client.Session({ open_viewer: isDev });
await session.use(async () => {
  await session.execute({ type: "goto", url: "https://example.com" });
});

const status = await session.status();

export { status };
