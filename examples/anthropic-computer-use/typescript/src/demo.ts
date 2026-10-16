import { randomBytes } from 'node:crypto';
import Anthropic from '@anthropic-ai/sdk';
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';
import { NotteComputer } from './computer.ts';

export async function runDemo() {
  const client = new NotteClient();
  return client.Session({ max_duration_minutes: 3, viewport_width: 1024, viewport_height: 768 }).use(async (session) => {
    const id = session.getId()!;
    try {
      const browser = await chromium.connectOverCDP(await session.cdpUrl());
      try {
        const page = browser.contexts()[0].pages()[0];
        await page.goto('about:blank');
        await page.setViewportSize({ width: 1024, height: 768 });
        const code = `orbit-${randomBytes(3).toString('hex')}`;
        await page.setContent(`<body style="font:28px Arial;padding:40px"><h1>Copy the code</h1><p>Code: ${code}</p><form onsubmit="event.preventDefault();document.querySelector('output').textContent=document.querySelector('input').value === '${code}'?'Accepted':'Wrong code'"><label>Code <input style="font-size:28px"></label><button>Submit</button></form><output></output></body>`);
        const signal = AbortSignal.timeout(120_000);
        const computer = new NotteComputer(page, () => page.url() === 'about:blank', signal);
        const calls: string[] = [];
        try {
          const runner = new Anthropic().beta.messages.toolRunner({
            model: 'claude-haiku-5-5', max_tokens: 1024, max_iterations: 8,
            tools: [computer],
            messages: [{ role: 'user', content: 'Take a screenshot. Enter the code shown on the page into its form, submit using Enter, and report the result. Use only computer tools.' }],
          }, { signal });
          for await (const message of runner) {
            for (const block of message.content) if (block.type === 'tool_use') calls.push(block.name);
          }
          const output = await page.locator('output').innerText();
          if (output !== 'Accepted' || await page.locator('input').inputValue() !== code) {
            throw new Error('The computer agent did not complete the form');
          }
          return { output, session_id: id, calls };
        } finally {
          await computer.close();
        }
      } finally {
        await browser.close();
      }
    } catch {
      throw new Error(`Computer use failed (session ${id})`);
    }
  });
}
