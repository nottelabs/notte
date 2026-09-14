// @sniptest filename=cdp_playwright.ts
// @sniptest show=1-18
import { NotteClient } from "notte-sdk";
import { chromium } from "playwright-core";

const client = new NotteClient();
const session = client.Session({ proxies: false });
await session.use(async (session) => {
  // Get CDP URL
  const cdpUrl = await session.cdpUrl();
  const browser = await chromium.connectOverCDP(cdpUrl);
  try {
    const page = browser.contexts()[0].pages()[0];
    await page.goto("https://www.google.com");
    const screenshot = await page.screenshot({ path: "screenshot.png" });
    if (!screenshot) throw new Error("Screenshot was not returned");
  } finally {
    await browser.close();
  }
});

const status = await session.status();
export { status };
