import { writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { withNotteVibium } from './connection.ts';

export async function runDemo(options: { url?: string; selector?: string; signal?: AbortSignal } = {}) {
  return withNotteVibium(async (driver, bidiUrl, sessionId, signal) => {
    let remote = await driver.connect(bidiUrl, signal);
    const page = await remote.page();
    await page.go(options.url ?? 'https://example.com');
    const text = await (await page.find(options.selector ?? 'h1', { timeout: 1_000 })).text();
    const title = await page.title();
    const png = await page.screenshot();
    if (!png.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) throw new Error('Expected a PNG screenshot');
    await driver.disconnect(remote);
    remote = await driver.connect(bidiUrl, signal);
    if (await (await remote.page()).title() !== title) throw new Error('Native reconnect changed the page');
    await driver.disconnect(remote);
    return { session_id: sessionId, title, text, png };
  }, { signal: options.signal });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  process.on('SIGINT', abort);
  process.on('SIGTERM', abort);
  try {
    const { png, ...result } = await runDemo({ signal: controller.signal });
    await writeFile('screenshot.png', png);
    console.log(JSON.stringify({ ...result, screenshot: 'screenshot.png' }));
  } catch (error) {
    console.error(error instanceof Error ? error.message : 'Vibium failed');
    process.exitCode = controller.signal.aborted ? 130 : 1;
  } finally {
    process.off('SIGINT', abort);
    process.off('SIGTERM', abort);
  }
}
