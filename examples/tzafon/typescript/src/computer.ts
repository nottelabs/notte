import { setTimeout as sleep } from 'node:timers/promises';
import type Lightcone from '@tzafon/lightcone';
import type { ResponseCreateParams, ResponseComputerToolCall } from '@tzafon/lightcone/resources/responses';
import type { Page, Browser } from 'playwright-core';

export const MODEL = 'tzafon.northstar-cua-fast-1.6';
export type Action = ResponseComputerToolCall['action'];
export function pixel(value: number, dimension: number) {
  if (!Number.isFinite(value) || value < 0 || value > 999) throw new Error('Expected a model coordinate from 0 to 999');
  return Math.floor(value * dimension / 1000);
}
export async function withBrowserDeadline<T>(browser: Pick<Browser, 'close'>, signal: AbortSignal, work: () => Promise<T>): Promise<T> {
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
  const aborted = new Promise<never>((_, reject) => {
    abort = () => { void close().catch(() => {}); reject(signal.reason); };
    signal.addEventListener('abort', abort, { once: true });
  });
  let failed = false;
  try {
    signal.throwIfAborted();
    const pending = (async () => work())();
    return await Promise.race([pending, aborted]);
  } catch (error) {
    failed = true;
    throw error;
  } finally {
    signal.removeEventListener('abort', abort);
    try { await close(); }
    catch { if (!failed) throw new Error('Browser disconnect failed'); }
  }
}

export class NotteComputer {
  readonly actions: string[] = [];
  readonly page: Page;
  readonly approve: (action: Action) => boolean | Promise<boolean>;
  readonly signal: AbortSignal;
  constructor(page: Page, approve: (action: Action) => boolean | Promise<boolean>, signal: AbortSignal) {
    this.page = page;
    this.approve = approve;
    this.signal = signal;
    if (!page.viewportSize()) throw new Error('Set a browser viewport');
  }
  async screenshot() {
    this.signal.throwIfAborted();
    const image = await this.page.screenshot({ type: 'png', scale: 'css' });
    this.signal.throwIfAborted();
    return `data:image/png;base64,${image.toString('base64')}`;
  }
  private async approval(action: Action) {
    this.signal.throwIfAborted();
    let abort!: () => void;
    const cancelled = new Promise<never>((_, reject) => {
      abort = () => reject(this.signal.reason);
      this.signal.addEventListener('abort', abort, { once: true });
    });
    try {
      const allowed = await Promise.race([Promise.resolve().then(() => this.approve(action)), cancelled]);
      this.signal.throwIfAborted();
      return allowed;
    } finally { this.signal.removeEventListener('abort', abort); }
  }
  async handle(call: ResponseComputerToolCall): Promise<ResponseCreateParams.ComputerCallOutput> {
    if (call.pending_safety_checks?.length) throw new Error('Safety review is required');
    const action = call.action;
    if (!await this.approval(action)) throw new Error('Computer action refused');
    if ((action.type === 'type' || action.type === 'point_and_type') && (typeof action.text !== 'string' || action.text.length > 1000)) throw new Error('Text exceeds the form limit');
    if (action.type === 'click' || action.type === 'point_and_type') {
      const viewport = this.page.viewportSize();
      if (!viewport) throw new Error('Missing browser viewport');
      if (action.type === 'click' && action.button !== 'left') throw new Error('This form example only permits left clicks');
      await this.page.mouse.click(pixel(action.x, viewport.width), pixel(action.y, viewport.height));
    }
    this.signal.throwIfAborted();
    switch (action.type) {
      case 'type': case 'point_and_type':
        await this.page.keyboard.insertText(action.text); break;
      case 'keypress':
        if (!action.keys.length || !action.keys.every(key => ['ENTER', 'RETURN', 'TAB'].includes(key.toUpperCase()))) throw new Error('This form example only permits Enter and Tab');
        for (const key of action.keys) {
          this.signal.throwIfAborted();
          await this.page.keyboard.press(key.toUpperCase() === 'TAB' ? 'Tab' : 'Enter');
        }
        break;
      case 'wait': await sleep(250, undefined, { signal: this.signal }); break;
      case 'screenshot': case 'click': break;
      default: throw new Error('Unsupported form action');
    }
    this.signal.throwIfAborted();
    this.actions.push(action.type);
    return { type: 'computer_call_output', call_id: call.call_id, output: { type: 'computer_screenshot', image_url: await this.screenshot() } };
  }
  async run(provider: Lightcone, task: string) {
    const viewport = this.page.viewportSize()!;
    // Current API docs use computer_use; the pinned SDK still types the legacy tool name.
    const tools = [{ type: 'computer_use', environment: 'browser', display_width: viewport.width, display_height: viewport.height }] as unknown as ResponseCreateParams['tools'];
    const history: Exclude<ResponseCreateParams['input'], string> = [{ role: 'user', content: [{ type: 'input_text', text: task }, { type: 'input_image', image_url: await this.screenshot(), detail: 'auto' }] }];
    for (let turn = 0; turn < 9; turn++) {
      const response = await provider.responses.create({ model: MODEL, tools, input: history, store: false, max_output_tokens: 2048 }, { signal: this.signal });
      if (response.status !== 'completed') throw new Error('Model response did not complete');
      const output = response.output ?? [];
      const calls = output.filter((item): item is ResponseComputerToolCall => item.type === 'computer_call');
      if (!calls.length) {
        if (!output.some(item => item.type === 'message')) throw new Error('Model returned neither actions nor a message');
        return;
      }
      if (turn === 8 || this.actions.length + calls.length > 32) throw new Error('Computer action limit exceeded');
      history.push(...output as typeof history);
      for (const call of calls) history.push(await this.handle(call));
    }
  }
}
