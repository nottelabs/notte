import { setTimeout as sleep } from 'node:timers/promises';
import {
  BetaAbstractComputerToolset20260801, ToolError,
  type BetaComputerConfirmCallable, type BetaScreenshotResult, type BetaToolsetCallContext,
} from '@anthropic-ai/sdk/helpers/beta/toolsets';
import type {
  BetaComputerKeyInput, BetaComputerLeftClickInput, BetaComputerTypeInput, BetaComputerWaitInput,
} from '@anthropic-ai/sdk/resources/beta';
import type { Page } from 'playwright-core';

export class NotteComputer extends BetaAbstractComputerToolset20260801 {
  readonly page: Page;
  private readonly signal?: AbortSignal;
  private cursor: [number, number] = [0, 0];

  constructor(page: Page, confirm: BetaComputerConfirmCallable, signal?: AbortSignal) {
    if (!page.viewportSize()) throw new Error('Set the Playwright viewport before creating the computer toolset');
    super({ confirm });
    this.page = page;
    this.signal = signal;
  }

  async screenshot(_context: BetaToolsetCallContext, _input: unknown): Promise<BetaScreenshotResult> {
    const image = await this.page.screenshot({ type: 'png', scale: 'css' });
    return { data: image.toString('base64'), mediaType: 'image/png' };
  }

  async left_click(_context: BetaToolsetCallContext, input: BetaComputerLeftClickInput): Promise<void> {
    if (input.text) throw new ToolError('Modifier clicks are not supported');
    const [x, y] = input.coordinate ?? this.cursor;
    const viewport = this.page.viewportSize();
    if (!viewport || !(0 <= x && x < viewport.width && 0 <= y && y < viewport.height)) {
      throw new ToolError('Click coordinates are outside the page viewport');
    }
    await this.page.mouse.click(x, y);
    this.cursor = [x, y];
  }

  async type_(_context: BetaToolsetCallContext, input: BetaComputerTypeInput): Promise<void> {
    await this.page.keyboard.insertText(input.text);
  }

  async key(_context: BetaToolsetCallContext, input: BetaComputerKeyInput): Promise<void> {
    const aliases: Record<string, string> = { Return: 'Enter', ctrl: 'Control', alt: 'Alt', shift: 'Shift', super: 'Meta' };
    const keys = input.text.split('+').map(part => aliases[part] ?? part).join('+');
    const repeat = input.repeat ?? 1;
    if (!Number.isInteger(repeat) || repeat < 1 || repeat > 100) throw new ToolError('Key repeat must be between 1 and 100');
    for (let index = 0; index < repeat; index++) await this.page.keyboard.press(keys);
  }

  async wait(_context: BetaToolsetCallContext, input: BetaComputerWaitInput): Promise<void> {
    if (!(0 <= input.duration && input.duration <= 300)) throw new ToolError('Wait duration must be between 0 and 300 seconds');
    await sleep(input.duration * 1000, undefined, { signal: this.signal });
  }
}
