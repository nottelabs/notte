import { initLogger } from 'braintrust';
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';

export async function runDemo(url = 'https://example.com') {
  if (!process.env.BRAINTRUST_API_KEY) throw new Error('Set BRAINTRUST_API_KEY');
  const logger = initLogger({ projectName: process.env.BRAINTRUST_PROJECT ?? 'notte-integration-tests' });
  const client = new NotteClient();
  let sessionId = 'not-created';
  let stage = 'create browser';
  try {
    return await logger.traced(async span => {
      try {
        const title = await client.Session({ max_duration_minutes: 3 }).use(async session => {
          sessionId = session.getId()!;
          span.log({ metadata: { session_id: sessionId } });
          stage = 'navigate';
          const browser = await chromium.connectOverCDP(await session.cdpUrl());
          try {
            const page = browser.contexts()[0].pages()[0];
            await page.goto(url, { timeout: 30_000 });
            return await page.title();
          } finally { await browser.close(); }
        });
        span.log({ output: { title } });
        return { title, session_id: sessionId, span_id: span.id, trace_url: await span.permalink() };
      } catch {
        throw new Error(`Browser task failed: ${stage} (session ${sessionId})`);
      }
    }, { name: 'notte.browser', event: { input: { url } } });
  } finally { await logger.flush(); }
}
