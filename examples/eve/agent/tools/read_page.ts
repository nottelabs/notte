import { defineTool } from 'eve/tools';
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';
import { z } from 'zod';

export default defineTool({
  description: 'Open a web page in a fresh Notte browser and return its title.',
  inputSchema: z.object({ url: z.url({ protocol: /^https?$/ }) }),
  async execute({ url }, ctx) {
    ctx.abortSignal.throwIfAborted();
    return new NotteClient().Session({ max_duration_minutes: 3 }).use(async session => {
      try {
        const browser = await chromium.connectOverCDP(await session.cdpUrl());
        try {
          ctx.abortSignal.throwIfAborted();
          const page = await browser.contexts()[0].newPage();
          await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
          ctx.abortSignal.throwIfAborted();
          return { title: await page.title(), session_id: session.getId()! };
        } finally { await browser.close(); }
      } catch {
        throw new Error(`Notte browser task failed (session ${session.getId()})`);
      }
    });
  },
});
