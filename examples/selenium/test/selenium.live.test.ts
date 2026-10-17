import assert from 'node:assert/strict';
import { test } from 'node:test';
import { NotteClient, sessionStatus } from 'notte-sdk';
import { By, until, error } from 'selenium-webdriver';
import { cdpBridge } from '../src/bridge.ts';
import { connectDriver, main } from '../src/main.ts';

async function owned(run: () => Promise<void>) {
  assert.ok(process.env.NOTTE_API_URL, 'Choose the test API explicitly');
  const original = globalThis.fetch;
  const ids: string[] = [];
  globalThis.fetch = async (input, options) => {
    const response = await original(input, options);
    const url = new URL(input instanceof Request ? input.url : String(input));
    if (url.pathname === '/sessions/start' && response.ok) ids.push((await response.clone().json()).session_id);
    return response;
  };
  try { await run(); }
  finally {
    globalThis.fetch = original;
    assert.equal(ids.length, 1, 'Expected exactly one owned browser');
    const client = new NotteClient();
    let closed = false;
    const signal = AbortSignal.timeout(15_000);
    while (!signal.aborted) {
      const result = await sessionStatus({ client: client.getClient(), path: { session_id: ids[0] }, throwOnError: true, signal });
      if (result.data.status === 'closed') { closed = true; break; }
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    assert.ok(closed, 'Owned browser did not close');
  }
}

test('Selenium with a hosted Notte browser', { skip: process.env.NOTTE_SELENIUM_LIVE !== '1', timeout: 240_000 }, async t => {
  await t.test('original demo', () => owned(async () => assert.equal(await main(), 'Example Domain')));
  await t.test('standard actions and reconnect', () => owned(async () => {
    await new NotteClient().Session({ max_duration_minutes: 3, proxies: false, browser_type: 'chrome', viewport_width: 1024, viewport_height: 768 }).use(async session => {
      const bridge = await cdpBridge(await session.cdpUrl());
      try {
        let driver = await connectDriver(bridge.address);
        try {
          await driver.manage().setTimeouts({ pageLoad: 30_000 });
          await driver.get('https://example.com');
          assert.equal(await driver.getTitle(), 'Example Domain');
          await driver.executeScript("document.body.innerHTML='<input id=name><button id=submit>Send</button>'; document.querySelector('#submit').onclick=event=>event.target.textContent='Sent'");
          const field = await driver.wait(until.elementLocated(By.id('name')), 10_000);
          await driver.wait(until.elementIsVisible(field), 10_000);
          await field.sendKeys('Notte');
          await driver.actions().move({ origin: await driver.findElement(By.id('submit')) }).click().perform();
          assert.equal(await driver.findElement(By.id('submit')).getText(), 'Sent');
        } finally { await driver.quit(); }
        driver = await connectDriver(bridge.address);
        try { assert.equal(await driver.findElement(By.id('name')).getAttribute('value'), 'Notte'); }
        finally { await driver.quit(); }
        const metadata = await (await fetch(`http://${bridge.address}/json/version`)).json();
        assert.ok(metadata.webSocketDebuggerUrl.startsWith(`ws://${bridge.address}/`));
        assert.ok(!JSON.stringify(metadata).includes(await session.cdpUrl()));
        assert.equal((await fetch(`http://${bridge.address}/json/version`, { headers: { Origin: 'https://example.com' } })).status, 403);
      } finally { await bridge.close(); }
      await assert.rejects(fetch(`http://${bridge.address}/json/version`));
    });
  }));
  await t.test('real command failure closes browser', () => owned(async () => {
    await assert.rejects(new NotteClient().Session({ max_duration_minutes: 3, proxies: false, browser_type: 'chrome' }).use(async session => {
      const bridge = await cdpBridge(await session.cdpUrl());
      try {
        const driver = await connectDriver(bridge.address);
        try { await driver.findElement(By.css('[')); }
        finally { await driver.quit(); }
      } finally { await bridge.close(); }
    }), error.InvalidSelectorError);
  }));
});
