import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';

class WatsonxExampleError extends Error {}
class HttpError extends Error {
  status: number;
  constructor(status: number) { super('IBM request failed'); this.status = status; }
}

function safeFailure(error: unknown, stage: string, sessionId: string) {
  if (error instanceof WatsonxExampleError) return error;
  const name = error instanceof Error ? error.constructor.name : 'UnknownError';
  const category = /^[A-Za-z][A-Za-z0-9]{0,63}$/.test(name) ? name : 'Error';
  const detail = error instanceof HttpError ? ` HTTP ${error.status}` : '';
  return new WatsonxExampleError(`Screenshot analysis failed: ${stage} [${category}]${detail} (session ${sessionId})`);
}

export async function describe(image: Buffer, fetchImpl: typeof fetch = fetch) {
  const token = await fetchImpl('https://iam.cloud.ibm.com/identity/token', {
    method: 'POST', body: new URLSearchParams({ grant_type: 'urn:ibm:params:oauth:grant-type:apikey', apikey: process.env.WATSONX_API_KEY! }),
    redirect: 'error', signal: AbortSignal.timeout(30_000),
  });
  if (!token.ok) throw new HttpError(token.status);
  const { access_token } = await token.json() as { access_token?: unknown };
  if (typeof access_token !== 'string' || !access_token) throw new Error('IBM IAM did not return an access token');
  const response = await fetchImpl(`${(process.env.WATSONX_URL ?? 'https://us-south.ml.cloud.ibm.com').replace(/\/$/, '')}/ml/v1/text/chat?version=2024-05-31`, {
    method: 'POST', headers: { Authorization: `Bearer ${access_token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      project_id: process.env.WATSONX_PROJECT_ID, model_id: process.env.WATSONX_MODEL_ID,
      messages: [{ role: 'user', content: [
        { type: 'text', text: 'Describe the visible page heading in one sentence.' },
        { type: 'image_url', image_url: { url: `data:image/png;base64,${image.toString('base64')}` } },
      ] }], max_tokens: 200,
    }), redirect: 'error', signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok) throw new HttpError(response.status);
  const result = await response.json() as { choices?: { message?: { content?: string } }[] };
  const description = result.choices?.[0]?.message?.content;
  if (typeof description !== 'string' || !description.trim()) throw new Error('The vision model did not return text');
  return description;
}

export async function runDemo(fetchImpl: typeof fetch = fetch) {
  for (const name of ['WATSONX_API_KEY', 'WATSONX_PROJECT_ID', 'WATSONX_MODEL_ID']) {
    if (!process.env[name]) throw new Error(`Set ${name}`);
  }
  const client = new NotteClient();
  let sessionId = 'not-created';
  let stage = 'create browser';
  let description = '';
  try {
    await client.Session({ max_duration_minutes: 3 }).use(async session => {
      sessionId = session.getId()!;
      try {
        stage = 'capture page';
        const browser = await chromium.connectOverCDP(await session.cdpUrl());
        let failed = false;
        try {
          const page = browser.contexts()[0].pages()[0];
          await page.goto('https://example.com', { waitUntil: 'domcontentloaded' });
          await page.locator('body').waitFor();
          const image = await page.screenshot({ type: 'png' });
          stage = 'describe screenshot';
          description = await describe(image, fetchImpl);
        } catch (error) {
          failed = true;
          throw error;
        } finally {
          if (!failed) stage = 'disconnect browser';
          let timer: ReturnType<typeof setTimeout> | undefined;
          try {
            await Promise.race([
              browser.close(),
              new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('Close deadline exceeded')), 5000); }),
            ]);
          } catch {
            if (!failed) throw new Error('Browser disconnect failed');
          } finally { clearTimeout(timer); }
        }
      } catch (error) { throw safeFailure(error, stage, sessionId); }
    });
    return { description, session_id: sessionId };
  } catch (error) { throw safeFailure(error, stage, sessionId); }
}
