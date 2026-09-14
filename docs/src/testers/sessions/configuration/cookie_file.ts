// @sniptest filename=cookie_file.ts
// @sniptest show=1-10
import { NotteClient } from "notte-sdk";

const client = new NotteClient();

const session = client.Session({ cookie_file: "cookies.json" });
await session.use(async (session) => {
  const page = await session.page();
  await page.goto("https://example.com");
  // Cookies auto-loaded at start, auto-saved when session ends
});

const status = await session.status();
export { status };
