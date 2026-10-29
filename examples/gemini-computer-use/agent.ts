import { GoogleGenAI } from '@google/genai';
import { NotteClient } from 'notte-sdk';
import { chromium, type Page, type Browser } from 'playwright-core';
import { pathToFileURL } from 'node:url';

type Args = Record<string, unknown>;
class ApprovalRequired extends Error {}
function key(value: string): string {
  const aliases: Record<string, string> = { CTRL: 'Control', CMD: 'Meta', COMMAND: 'Meta', ALT: 'Alt', SHIFT: 'Shift', ESC: 'Escape', ENTER: 'Enter', TAB: 'Tab', BACKSPACE: 'Backspace', SPACE: 'Space', DELETE: 'Delete' };
  return value.split('+').map(part => aliases[part.toUpperCase()] ?? part).join('+');
}

const viewport = { width: 1440, height: 900 };

// Give a new tab the computer viewport. Tabs in the window the first page sized already share it.
async function fit(page: Page): Promise<void> {
  await page.waitForLoadState('domcontentloaded', { timeout: 30_000 });
  const [width, height] = await page.evaluate(() => [innerWidth, innerHeight]);
  if (width !== viewport.width || height !== viewport.height) await page.setViewportSize(viewport);
}

export async function execute(page: Page, name: string, args: Args): Promise<void> {
  const safety = args.safety_decision as { decision?: string } | undefined;
  if (safety !== undefined && safety !== null && !['allowed', 'regular'].includes(safety.decision ?? '')) {
    throw new ApprovalRequired('Computer action requires approval or was blocked');
  }
  // A tab sharing the sized window has no Playwright viewport of its own.
  const size = page.viewportSize() ?? viewport;
  const point = (prefix = ''): [number, number] => {
    const x = args[`${prefix}x`], y = args[`${prefix}y`];
    if (typeof x !== 'number' || typeof y !== 'number' || !Number.isFinite(x) || !Number.isFinite(y)
      || x < 0 || y < 0 || x > 999 || y > 999) throw new Error('Invalid computer coordinates');
    return [Math.floor(x * size.width / 1000), Math.floor(y * size.height / 1000)];
  };
  if (['click', 'double_click', 'triple_click', 'middle_click', 'right_click'].includes(name)) {
    await page.mouse.click(...point(), {
      button: name === 'middle_click' ? 'middle' : name === 'right_click' ? 'right' : 'left',
      clickCount: name === 'double_click' ? 2 : name === 'triple_click' ? 3 : 1,
    });
  } else if (['move', 'mouse_down', 'mouse_up'].includes(name)) {
    await page.mouse.move(...point());
    if (name === 'mouse_down') await page.mouse.down();
    if (name === 'mouse_up') await page.mouse.up();
  } else if (name === 'drag_and_drop') {
    const start = point('start_'), end = point('end_');
    await page.mouse.move(...start);
    await page.mouse.down();
    try { await page.mouse.move(...end, { steps: 10 }); }
    finally { await page.mouse.up(); }
  } else if (name === 'type') {
    await page.keyboard.insertText(args.text as string);
    if (args.press_enter) await page.keyboard.press('Enter');
  } else if (['press_key', 'key_down', 'key_up', 'hotkey'].includes(name)) {
    if (name === 'hotkey') await page.keyboard.press((args.keys as string[]).map(key).join('+'));
    else await page.keyboard[name === 'press_key' ? 'press' : name === 'key_down' ? 'down' : 'up'](key(args.key as string));
  } else if (name === 'scroll') {
    await page.mouse.move(...point());
    const distance = args.magnitude_in_pixels ?? 300;
    if (typeof distance !== 'number' || !Number.isFinite(distance) || distance < 0 || distance > 999) {
      throw new Error('Invalid scroll distance');
    }
    const delta: Record<string, [number, number]> = {
      up: [0, -distance], down: [0, distance], left: [-distance, 0], right: [distance, 0],
    };
    if (!delta[args.direction as string]) throw new Error('Invalid scroll direction');
    await page.mouse.wheel(...delta[args.direction as string]);
  } else if (name === 'navigate') {
    const url = args.url as string;
    if (!/^https?:\/\//.test(url)) throw new Error('Only HTTP browser navigation is supported');
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
  } else if (['go_back', 'go_forward'].includes(name)) {
    await page[name === 'go_back' ? 'goBack' : 'goForward']({ waitUntil: 'domcontentloaded', timeout: 30_000 });
  } else if (name === 'wait') {
    const seconds = args.seconds ?? 1;
    if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0 || seconds > 5) {
      throw new Error('Wait must be between zero and five seconds');
    }
    await new Promise(resolve => setTimeout(resolve, seconds * 1000));
  } else if (name !== 'take_screenshot') {
    throw new Error('Unsupported computer action');
  }
}

export async function perform(page: Page, name: string, args: Args): Promise<Page> {
  const popup = ['click', 'double_click', 'middle_click', 'type', 'press_key', 'hotkey'].includes(name)
    ? page.context().waitForEvent('page', { timeout: 1000 }).catch(() => undefined) : undefined;
  await execute(page, name, args);
  const destination = await popup;
  if (!destination) return page;
  await fit(destination);
  return destination;
}

export async function run(task: string, initialUrl = 'https://example.com') {
  if (!process.env.GEMINI_API_KEY) throw new Error('Set GEMINI_API_KEY');
  const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY, httpOptions: { timeout: 60_000, retryOptions: { attempts: 1 } } });
  const model = process.env.GEMINI_MODEL ?? 'gemini-3.8-flash';
  const tools = [{ type: 'computer_use' as const, environment: 'browser' as const, enable_prompt_injection_detection: true }];
  return new NotteClient().Session({ max_duration_minutes: 3 }).use(async session => {
    let browser: Browser | undefined;
    let failed = false;
    try {
      browser = await chromium.connectOverCDP(await session.cdpUrl());
      let page = await browser.contexts()[0].newPage();
      await page.setViewportSize(viewport);
      await page.goto(initialUrl, { waitUntil: 'domcontentloaded', timeout: 30_000 });
      let activePage = page;
      page.context().on('page', destination => { activePage = destination; });
      const refreshPage = async () => {
        if (activePage === page || activePage.isClosed()) return false;
        page = activePage;
        await fit(page);
        return true;
      };
      let interaction = await ai.interactions.create({
        model, tools,
        input: [
          { type: 'text', text: task },
          { type: 'image', data: (await page.screenshot()).toString('base64'), mime_type: 'image/png' },
        ],
      });
      let actions = 0;
      for (let turn = 0; turn <= 12; turn++) {
        let changed = await refreshPage();
        const calls = interaction.steps.filter(step => step.type === 'function_call');
        if (!calls.length) {
          if (changed && turn < 12) {
            interaction = await ai.interactions.create({ model, tools, previous_interaction_id: interaction.id, input: [
              { type: 'text', text: 'A new browser tab opened. Continue the original task using this screenshot.' },
              { type: 'image', data: (await page.screenshot()).toString('base64'), mime_type: 'image/png' },
            ] });
            continue;
          }
          if (changed) throw new Error('Computer task exceeded twelve turns');
          if (interaction.status !== 'completed') throw new Error('Computer task did not complete');
          const answer = interaction.steps.flatMap(step => step.type === 'model_output'
            ? (step.content ?? []).filter(part => part.type === 'text').map(part => part.text) : []).join(' ');
          return { answer, title: await page.title(), session_id: session.getId()!, actions };
        }
        if (turn === 12) throw new Error('Computer task exceeded twelve turns');
        const results = [];
        for (const call of calls) {
          changed = await refreshPage() || changed;
          const previousPage = page, executed = !changed;
          if (executed) {
            page = await perform(page, call.name!, call.arguments as Args);
            actions++;
            await refreshPage();
          }
          const state = { url: page.url(), ...(executed ? {} : { note: 'A new tab opened; this action was not executed. Use the current screenshot.' }) };
          results.push({ type: 'function_result' as const, name: call.name, call_id: call.id, result: [
            { type: 'text' as const, text: JSON.stringify(state) },
            { type: 'image' as const, data: (await page.screenshot()).toString('base64'), mime_type: 'image/png' as const },
          ] });
          changed = changed || page !== previousPage;
        }
        interaction = await ai.interactions.create({
          model, tools, previous_interaction_id: interaction.id, input: results,
        });
      }
      throw new Error('Computer task exceeded twelve turns');
    } catch (error) {
      failed = true;
      if (error instanceof ApprovalRequired) throw error;
      const failure = error as { status?: number; statusCode?: number };
      const code = failure?.status ?? failure?.statusCode;
      if (typeof code === 'number') {
        throw new Error(`Gemini API error ${code}`);
      }
      throw new Error('Gemini computer task failed');
    } finally {
      if (browser) {
        let timer: ReturnType<typeof setTimeout> | undefined;
        try {
          await Promise.race([
            browser.close(),
            new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('Close deadline exceeded')), 5000); }),
          ]);
        } catch {
          if (!failed) throw new Error('Gemini browser cleanup failed');
        } finally { clearTimeout(timer); }
      }
    }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  console.log(JSON.stringify(await run(process.argv.slice(2).join(' ') || 'Go to https://example.com and read its page title.')));
}
