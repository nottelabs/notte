// @sniptest filename=connect_url.ts
// @sniptest show=4-21
const apiKey = process.env.NOTTE_API_KEY!;
const connectUrl = `${(process.env.NOTTE_API_URL ?? "https://api.notte.cc").replace("https://", "wss://")}/sessions/connect`;

import { chromium } from "playwright-core";

// connectUrl is "wss://api.notte.cc/sessions/connect"
// Pass your API key and session options in the query string
const query = new URLSearchParams({ token: apiKey, proxies: "false", max_duration_minutes: "10" });
const url = `${connectUrl}?${query}`;

// Connecting starts a new Notte session
const browser = await chromium.connectOverCDP(url);
let title: string;
try {
  const page = browser.contexts()[0].pages()[0];
  await page.goto("https://example.com");
  title = await page.title();
} finally {
  // Closing the connection stops the session
  await browser.close();
}

const results = [title];
export { results };
