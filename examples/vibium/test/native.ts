// Used only by the isolated local-browser acceptance test, never a Notte endpoint.
import assert from 'node:assert/strict';
import { cdpBridge } from '../src/bridge.ts';
import { interrupted, NativeDriver } from '../src/connection.ts';

const driver = new NativeDriver();
const signal = AbortSignal.timeout(60_000);
try {
  await driver.start(signal);
  const bridge = await cdpBridge(process.env.VIBIUM_TEST_CDP!, signal);
  try {
    const bidi = await driver.attach(bridge.address, signal);
    let remote = await driver.connect(bidi, signal);
    const page = await remote.page();
    const html = `<title>Owned native fixture</title><input id="value"><button id="copy"
onclick="document.querySelector('output').textContent=document.querySelector('input').value">Copy</button><output></output>`;
    await page.go(`data:text/html,${encodeURIComponent(html)}`);
    await (await page.find('#value')).fill('native-typescript');
    await (await page.find('#copy')).click();
    assert.equal(await (await page.find('output')).text(), 'native-typescript');
    const png = await page.screenshot();
    assert.ok(png.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])));
    assert.ok(png.length > 100);
    await driver.disconnect(remote);
    remote = await driver.connect(bidi, signal);
    assert.equal(await (await remote.page()).title(), 'Owned native fixture');
    await assert.rejects((await remote.page()).find('#absent-owned-fixture', { timeout: 250 }));
    const controller = new AbortController();
    const command = (await remote.page()).find('#cancelled-owned-fixture', { timeout: 30_000 });
    setTimeout(() => controller.abort(), 100);
    await assert.rejects(interrupted(command, controller.signal), /Browser task interrupted/);
  } finally {
    // Stop clients while their owned local transport still exists.
    await driver.close();
    await bridge.close();
  }
} finally { await driver.close(); }
