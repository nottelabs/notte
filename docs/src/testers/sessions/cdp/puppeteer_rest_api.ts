import puppeteer from 'puppeteer-core';
import { NotteClient } from 'notte-sdk';

const client = new NotteClient(); // reads NOTTE_API_KEY

// use() starts the session and always stops it when the callback ends
await client.Session({ idle_timeout_minutes: 10 }).use(async session => {
  const cdpUrl = await session.cdpUrl();

  // Connect Puppeteer
  const browser = await puppeteer.connect({ browserWSEndpoint: cdpUrl });

  try {
    const pages = await browser.pages();
    const page = pages[0];

    // Use Puppeteer
    await page.goto('https://example.com');
    console.log('Title:', await page.title());
  } finally {
    await browser.disconnect();
  }
});
