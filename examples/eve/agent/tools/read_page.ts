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
        let closing: Promise<void> | undefined;
        const close = () => closing ??= (async () => {
          let timer: ReturnType<typeof setTimeout> | undefined;
          try {
            await Promise.race([browser.close(), new Promise<never>((_, reject) => {
              timer = setTimeout(() => reject(new Error('Browser disconnect timed out')), 5_000);
            })]);
          } finally { clearTimeout(timer); }
        })();
        let abort!: () => void;
        const cancelled = new Promise<never>((_, reject) => {
          abort = () => { void close().catch(() => {}); reject(ctx.abortSignal.reason); };
          ctx.abortSignal.addEventListener('abort', abort, { once: true });
        });
        let failed = false;
        try {
          ctx.abortSignal.throwIfAborted();
          const work = (async () => {
            const page = await browser.contexts()[0].newPage();
            ctx.abortSignal.throwIfAborted();
            await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
            ctx.abortSignal.throwIfAborted();
            const title = await page.title();
            ctx.abortSignal.throwIfAborted();
            return { title, session_id: session.getId()! };
          })();
          return await Promise.race([work, cancelled]);
        } catch (error) {
          failed = true;
          throw error;
        } finally {
          ctx.abortSignal.removeEventListener('abort', abort);
          try { await close(); }
          catch { if (!failed) throw new Error('Browser disconnect failed'); }
        }
      } catch {
        throw new Error(`Notte browser task failed (session ${session.getId()})`);
      }
    }, { signal: ctx.abortSignal });
  },
});
