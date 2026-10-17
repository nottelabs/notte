import { task } from '@trigger.dev/sdk';
import { NotteClient } from 'notte-sdk';
import { chromium, type Browser } from 'playwright-core';

export async function readPage(payload: { url: string }) {
  return new NotteClient().Session({ max_duration_minutes: 3 }).use(async (session) => {
    let browser: Browser | undefined;
    let stage = 'browser connection';
    let failed = false;
    try {
      browser = await chromium.connectOverCDP(await session.cdpUrl());
      const page = await browser.contexts()[0].newPage();
      stage = 'navigation';
      await page.goto(payload.url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
      stage = 'reading the title';
      return { title: await page.title(), session_id: session.getId()! };
    } catch {
      failed = true;
      // Connection errors can include the authenticated CDP URL.
      throw new Error(`Notte browser task failed during ${stage} (session ${session.getId()})`);
    } finally {
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        if (browser) await Promise.race([
          browser.close(),
          new Promise<never>((_resolve, reject) => { timer = setTimeout(() => reject(new Error('Disconnect deadline')), 5_000); }),
        ]);
      }
      catch {
        if (!failed) throw new Error(`Notte browser cleanup failed (session ${session.getId()})`);
      }
      finally { clearTimeout(timer); }
    }
  });
}

export const readNottePage = task({
  id: 'notte-read-page',
  retry: { maxAttempts: 3 },
  run: readPage,
});
