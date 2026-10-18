import { randomBytes } from 'node:crypto';
import Anthropic from '@anthropic-ai/sdk';
import { NotteClient } from 'notte-sdk';
import { chromium, type Browser } from 'playwright-core';
import { NotteComputer } from './computer.ts';

export async function runDemo() {
  const client = new NotteClient();
  return client.Session({ max_duration_minutes: 3, viewport_width: 1024, viewport_height: 768 }).use(async (session) => {
    const id = session.getId()!;
    let stage = 'browser setup';
    let browser: Browser | undefined;
    let computer: NotteComputer | undefined;
    let failed = false;
    const signal = AbortSignal.timeout(120_000);
    try {
      browser = await chromium.connectOverCDP(await session.cdpUrl());
      const page = browser.contexts()[0].pages()[0];
      await page.goto('about:blank');
      await page.setViewportSize({ width: 1024, height: 768 });
      const code = `orbit-${randomBytes(3).toString('hex')}`;
      await page.setContent(`<body style="font:28px Arial;padding:40px"><h1>Copy the code</h1><p>Code: ${code}</p><form onsubmit="event.preventDefault();document.querySelector('output').textContent=document.querySelector('input').value === '${code}'?'Accepted':'Wrong code'"><label>Code <input style="font-size:28px"></label><button>Submit</button></form><output></output></body>`);
      computer = new NotteComputer(page, () => page.url() === 'about:blank', signal);
      const calls: string[] = [];
      stage = 'model request';
      const runner = new Anthropic().beta.messages.toolRunner({
        model: 'claude-haiku-5-5', max_tokens: 1024, max_iterations: 8,
        tools: [computer],
        messages: [{ role: 'user', content: 'Take a screenshot. Enter the code shown on the page into its form, submit using Enter, and report the result. Use only computer tools.' }],
      }, { signal });
      for await (const message of runner) {
        for (const block of message.content) if (block.type === 'tool_use') calls.push(block.name);
      }
      stage = 'verify page result';
      const output = await page.locator('output').innerText();
      if (output !== 'Accepted' || await page.locator('input').inputValue() !== code) {
        throw new Error('The computer agent did not complete the form');
      }
      return { output, session_id: id, calls };
    } catch (error) {
      failed = true;
      const category = signal.aborted || error instanceof Anthropic.APIConnectionTimeoutError || (error instanceof Error && error.name === 'TimeoutError')
        ? 'timeout' : error instanceof Anthropic.APIError ? `provider HTTP ${error.status ?? 'transport'}` : stage;
      throw new Error(`Computer use failed: ${category} (session ${id})`);
    } finally {
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        await Promise.race([
          (async () => { try { await computer?.close(); } finally { await browser?.close(); } })(),
          new Promise<never>((_resolve, reject) => { timer = setTimeout(() => reject(new Error('Disconnect deadline')), 5_000); }),
        ]);
      } catch {
        if (!failed) throw new Error(`Computer use cleanup failed (session ${id})`);
      } finally { clearTimeout(timer); }
    }
  });
}
