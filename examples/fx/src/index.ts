import { createFxEngine, type FxCustomProviderDefinition, type FxFetch } from 'libfx';
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';
import { pathToFileURL } from 'node:url';

export async function run(task: string, options: { provider?: FxCustomProviderDefinition; model?: string; fetch?: FxFetch } = {}) {
  return new NotteClient().Session({ max_duration_minutes: 3 }).use(async session => {
    try {
      const toolCompletions: Promise<void>[] = [];
      const engine = await createFxEngine({
        ...(options.provider ? { provider: options.provider } : { apiKey: process.env.AI_GATEWAY_API_KEY! }),
        model: options.model ?? process.env.FX_MODEL ?? 'anthropic/claude-haiku-5.5',
        backend: 'native',
        fetch: options.fetch,
        instructions: 'Use read_page to read a page title. Report only the observed title.',
        tools: [{
          name: 'read_page',
          description: 'Read the title of a page in this request\'s Notte browser.',
          inputSchema: { type: 'object', properties: { url: { type: 'string' } }, required: ['url'], additionalProperties: false },
          async execute({ url }: { url: string }, ctx) {
            let completed!: () => void;
            toolCompletions.push(new Promise<void>(resolve => { completed = resolve; }));
            try {
              ctx.signal.throwIfAborted();
              if (!['http:', 'https:'].includes(new URL(url).protocol)) throw new Error('Use an HTTP or HTTPS URL');
              const cdpUrl = await session.cdpUrl();
              ctx.signal.throwIfAborted();
              const browser = await chromium.connectOverCDP(cdpUrl);
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
                abort = () => { void close().catch(() => {}); reject(ctx.signal.reason); };
                ctx.signal.addEventListener('abort', abort, { once: true });
              });
              let failed = false;
              try {
                ctx.signal.throwIfAborted();
                const work = (async () => {
                  const page = await browser.contexts()[0].newPage();
                  ctx.signal.throwIfAborted();
                  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
                  ctx.signal.throwIfAborted();
                  const title = await page.title();
                  ctx.signal.throwIfAborted();
                  return { title };
                })();
                return await Promise.race([work, cancelled]);
              } catch (error) {
                failed = true;
                throw error;
              } finally {
                ctx.signal.removeEventListener('abort', abort);
                try { await close(); }
                catch { if (!failed) throw new Error('Browser disconnect failed'); }
              }
            } catch { throw new Error('Notte page navigation failed'); }
            finally { completed(); }
          },
        }],
      });
      try {
        const turn = engine.prompt(task, { signal: AbortSignal.timeout(90_000) });
        let answer = '';
        for await (const event of turn) if (event.type === 'text_delta') answer += event.delta;
        const result = await turn.result;
        if (result.stopReason !== 'end_turn') throw new Error('The fx turn did not complete');
        return { answer, session_id: session.getId()! };
      } finally {
        // A cancelled native turn can finish before its host tool's cleanup.
        await Promise.all(toolCompletions);
        await engine.close();
      }
    } catch {
      throw new Error(`fx browser task failed (session ${session.getId()})`);
    }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (!process.env.AI_GATEWAY_API_KEY) throw new Error('Set AI_GATEWAY_API_KEY');
  console.log(JSON.stringify(await run(process.argv.slice(2).join(' ') || 'Read the title of https://example.com')));
}
