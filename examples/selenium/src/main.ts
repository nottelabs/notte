import { NotteClient } from 'notte-sdk';
import { Builder } from 'selenium-webdriver';
import { Options, ServiceBuilder } from 'selenium-webdriver/chrome.js';
import { pathToFileURL } from 'node:url';
import { devNull } from 'node:os';
import { cdpBridge } from './bridge.ts';

export function connectDriver(address: string) {
  const path = process.env.CHROMEDRIVER_PATH;
  if (!path) throw new Error('Set CHROMEDRIVER_PATH to a matching ChromeDriver binary');
  const options = new Options();
  options.debuggerAddress(address);
  return new Builder().forBrowser('chrome')
    .setChromeOptions(options)
    .setChromeService(new ServiceBuilder(path).loggingTo(devNull))
    .build();
}

export async function main() {
  return new NotteClient().Session({ max_duration_minutes: 3, proxies: false, browser_type: 'chrome' }).use(async session => {
    const bridge = await cdpBridge(await session.cdpUrl());
    try {
      const driver = await connectDriver(bridge.address);
      try {
        await driver.manage().setTimeouts({ pageLoad: 30_000 });
        await driver.get('https://example.com');
        return await driver.getTitle();
      } finally { await driver.quit(); }
    } finally { await bridge.close(); }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  console.log(await main());
}
