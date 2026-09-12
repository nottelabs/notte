// @sniptest filename=selenium_builtin_page.ts
// @sniptest show=1-8
import { NotteClient } from "notte-sdk";

const client = new NotteClient();

const session = client.Session();
await session.use(async (session) => {
  const page = await session.page(); // Built-in Playwright page
});

const status = await session.status();
export { status };
