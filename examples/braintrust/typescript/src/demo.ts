import { initLogger } from 'braintrust';
import { NotteClient } from 'notte-sdk';
import { chromium, type Browser } from 'playwright-core';

class BrowserTaskError extends Error {}

export async function runDemo(url = 'https://example.com') {
  if (!process.env.BRAINTRUST_API_KEY) throw new Error('Set BRAINTRUST_API_KEY');
  const logger = initLogger({ projectName: process.env.BRAINTRUST_PROJECT ?? 'notte-integration-tests' });
  const client = new NotteClient();
  let sessionId = 'not-created';
  let stage = 'create browser';
  let failed = false;
  const browserError = (error: unknown) => {
    if (error instanceof BrowserTaskError) return error;
    const name = error instanceof Error ? error.constructor.name : 'UnknownError';
    let category = /^[A-Za-z][A-Za-z0-9]{0,63}$/.test(name) ? name : 'Error';
    const status = (error as { status?: unknown } | null)?.status;
    if (typeof status === 'number' && Number.isInteger(status)) category += ` HTTP ${status}`;
    return new BrowserTaskError(`Browser task failed: ${stage} [${category}] (session ${sessionId})`);
  };
  try {
    return await logger.traced(async span => {
      try {
        const title = await client.Session({ max_duration_minutes: 3 }).use(async session => {
          sessionId = session.getId()!;
          span.log({ metadata: { session_id: sessionId } });
          let browser: Browser | undefined;
          let browserFailed = false;
          try {
            stage = 'connect browser';
            browser = await chromium.connectOverCDP(await session.cdpUrl());
            stage = 'navigate';
            const page = browser.contexts()[0].pages()[0];
            await page.goto(url, { timeout: 30_000 });
            return await page.title();
          } catch (error) {
            browserFailed = true;
            throw browserError(error);
          } finally {
            if (browser) {
              if (!browserFailed) stage = 'disconnect browser';
              let timer: ReturnType<typeof setTimeout> | undefined;
              try {
                await Promise.race([
                  browser.close(),
                  new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('Close deadline exceeded')), 5000); }),
                ]);
              } catch {
                if (!browserFailed) throw browserError(new Error('Browser disconnect failed'));
              } finally { clearTimeout(timer); }
              if (!browserFailed) stage = 'release browser';
            }
          }
        });
        span.log({ output: { title } });
        return { title, session_id: sessionId, span_id: span.id, trace_url: await span.permalink() };
      } catch (error) {
        throw browserError(error);
      }
    }, { name: 'notte.browser', event: { input: { url } } });
  } catch (error) {
    failed = true;
    throw browserError(error);
  } finally {
    try { await logger.flush(); }
    catch {
      if (!failed) throw new Error(`Braintrust trace flush failed (session ${sessionId})`);
    }
  }
}
