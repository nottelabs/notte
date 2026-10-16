import { Laminar } from '@lmnr-ai/lmnr';
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';
import { pathToFileURL } from 'node:url';

export async function readPage(url = 'https://example.com') {
  return new NotteClient().Session({ max_duration_minutes: 3 }).use(async session => {
    const span = Laminar.startSpan({
      name: 'notte.read_page', input: { host: new URL(url).hostname }, sessionId: session.getId()!,
    });
    try {
      return await Laminar.withSpan(span, async () => {
        let stage = 'browser connection';
        try {
          const browser = await chromium.connectOverCDP(await session.cdpUrl());
          try {
            const page = await browser.contexts()[0].newPage();
            stage = 'navigation';
            await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
            stage = 'reading the title';
            const result = { title: await page.title(), session_id: session.getId()! };
            Laminar.setSpanOutput(result);
            return { ...result, trace_id: span.spanContext().traceId };
          } finally { await browser.close(); }
        } catch {
          span.setStatus({ code: 2 });
          throw new Error(`Notte browser task failed during ${stage} (session ${session.getId()}, trace ${span.spanContext().traceId})`);
        }
      });
    } finally { span.end(); }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (!process.env.LMNR_PROJECT_API_KEY) throw new Error('Set LMNR_PROJECT_API_KEY');
  Laminar.initialize({ projectApiKey: process.env.LMNR_PROJECT_API_KEY, instrumentModules: {} });
  try { console.log(JSON.stringify(await readPage(process.argv[2] ?? 'https://example.com'))); }
  finally { await Laminar.shutdown(); }
}
