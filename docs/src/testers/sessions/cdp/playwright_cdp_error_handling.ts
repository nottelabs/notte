// @sniptest filename=playwright_cdp_error_handling.ts
// @sniptest show=1-41
import { NotteClient } from 'notte-sdk';
import { chromium, type Browser } from 'playwright-core';

// Network failures before the WebSocket upgrade. An HTTP answer (403, 410, 503) is not one of them.
const TRANSPORT_ERRORS = [
  'socket hang up',
  'ECONNRESET',
  'ECONNREFUSED',
  'ETIMEDOUT',
  'Client network socket disconnected before secure TLS connection was established',
];

// Connect over CDP, once more if the connection dropped before the server answered.
async function connect(cdpUrl: string): Promise<Browser> {
  try {
    return await chromium.connectOverCDP(cdpUrl);
  } catch (error) {
    const firstLine = String(error).split('\n')[0];
    if (!TRANSPORT_ERRORS.some(transportError => firstLine.includes(transportError))) throw error;
  }
  await new Promise(resolve => setTimeout(resolve, 300));
  return chromium.connectOverCDP(cdpUrl);
}

const client = new NotteClient();

const status = await client.Session().use(async session => {
  const status = await session.status();
  const cdpUrl = status.cdp_url!;
  try {
    const browser = await connect(cdpUrl);
    try {
      // ... operations
      return status;
    } finally {
      await browser.close();
    }
  } catch (error) {
    console.log(`CDP connection failed: ${error}`);
  }
});

export { status };
