import { createFxEngine, type FxCustomProviderDefinition, type FxFetch } from 'libfx';
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';
import { pathToFileURL } from 'node:url';

export async function run(task: string, options: { provider?: FxCustomProviderDefinition; model?: string; fetch?: FxFetch } = {}) {
  return new NotteClient().Session({ max_duration_minutes: 3 }).use(async session => {
    try {
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
            try {
              ctx.signal.throwIfAborted();
              if (!['http:', 'https:'].includes(new URL(url).protocol)) throw new Error('Use an HTTP or HTTPS URL');
              const browser = await chromium.connectOverCDP(await session.cdpUrl());
              try {
                const page = await browser.contexts()[0].newPage();
                await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
                return { title: await page.title() };
              } finally { await browser.close(); }
            } catch { throw new Error('Notte page navigation failed'); }
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
      } finally { await engine.close(); }
    } catch {
      throw new Error(`fx browser task failed (session ${session.getId()})`);
    }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (!process.env.AI_GATEWAY_API_KEY) throw new Error('Set AI_GATEWAY_API_KEY');
  console.log(JSON.stringify(await run(process.argv.slice(2).join(' ') || 'Read the title of https://example.com')));
}
