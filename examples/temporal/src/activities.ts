import { NotteClient } from 'notte-sdk';
import { chromium, type Browser } from 'playwright-core';

export async function readPage({ url }: { url: string }) {
  return new NotteClient().Session({ max_duration_minutes: 3 }).use(async session => {
    let browser: Browser | undefined;
    let stage = 'browser connection';
    try {
      browser = await chromium.connectOverCDP(await session.cdpUrl());
      const page = await browser.contexts()[0].newPage();
      stage = 'navigation';
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
      stage = 'reading the title';
      return { title: await page.title(), session_id: session.getId()! };
    } catch {
      // Playwright errors can contain the authenticated CDP URL.
      throw new Error(`Notte activity failed during ${stage} (session ${session.getId()})`);
    } finally {
      await browser?.close();
    }
  });
}
