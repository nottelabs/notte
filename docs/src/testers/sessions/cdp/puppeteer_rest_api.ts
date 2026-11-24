import puppeteer, { type Browser } from 'puppeteer-core';
import { NotteClient } from 'notte-sdk';

// Network failures before the WebSocket upgrade. An HTTP answer (403, 410, 503) is not one of them.
const TRANSPORT_ERRORS = [
  'socket hang up',
  'ECONNRESET',
  'ECONNREFUSED',
  'ETIMEDOUT',
  'Client network socket disconnected before secure TLS connection was established',
];

// Connect Puppeteer, once more if the connection dropped before the server answered.
async function connect(browserWSEndpoint: string): Promise<Browser> {
  try {
    return await puppeteer.connect({ browserWSEndpoint });
  } catch (error) {
    // Puppeteer rejects with a WebSocket error event, not an Error: read its message
    const message = String((error as { message?: unknown }).message ?? error);
    if (!TRANSPORT_ERRORS.some(transportError => message.includes(transportError))) throw error;
  }
  await new Promise(resolve => setTimeout(resolve, 300));
  return puppeteer.connect({ browserWSEndpoint });
}

const client = new NotteClient(); // reads NOTTE_API_KEY

// use() starts the session and always stops it when the callback ends
await client.Session({ idle_timeout_minutes: 10 }).use(async session => {
  const cdpUrl = await session.cdpUrl();

  // Connect Puppeteer
  const browser = await connect(cdpUrl);

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
