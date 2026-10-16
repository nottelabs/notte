import { anthropic, createAgent, createTool } from '@inngest/agent-kit';
import { NotteClient } from 'notte-sdk';
import { chromium, type Browser } from 'playwright-core';
import { z } from 'zod';

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
      throw new Error(`Notte page read failed during ${stage} (session ${session.getId()})`);
    } finally {
      await browser?.close();
    }
  });
}

export const pageTitle = createTool({
  name: 'page_title',
  description: 'Read the current title of an HTTP or HTTPS page in a browser.',
  parameters: z.object({ url: z.url().refine(url => /^https?:/.test(url), 'Use HTTP or HTTPS') }),
  handler: readPage,
});

export const browserAgent = createAgent({
  name: 'Page reader',
  system: 'Use page_title once to read the URL the user provides. Do not guess the title.',
  model: anthropic({ model: 'claude-haiku-5-5', defaultParameters: { max_tokens: 512 } }),
  tools: [pageTitle],
});
