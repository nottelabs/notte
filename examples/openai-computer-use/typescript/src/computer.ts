import { setTimeout as sleep } from 'node:timers/promises';
import type { ResponseComputerToolCall, ResponseInputItem, ComputerAction } from 'openai/resources/responses/responses';
import type { Page } from 'playwright-core';

const keys: Record<string, string> = {
  ENTER: 'Enter', RETURN: 'Enter', TAB: 'Tab', ESC: 'Escape', ESCAPE: 'Escape', CTRL: 'Control', CONTROL: 'Control',
  ALT: 'Alt', SHIFT: 'Shift', META: 'Meta', SPACE: 'Space', BACKSPACE: 'Backspace', DELETE: 'Delete',
  ARROWLEFT: 'ArrowLeft', ARROWRIGHT: 'ArrowRight', ARROWUP: 'ArrowUp', ARROWDOWN: 'ArrowDown',
};

export class NotteComputer {
  readonly page: Page;
  readonly actions: string[] = [];
  readonly confirm: (action: ComputerAction) => boolean | Promise<boolean>;
  readonly signal?: AbortSignal;

  constructor(page: Page, confirm: (action: ComputerAction) => boolean | Promise<boolean>, signal?: AbortSignal) {
    if (!page.viewportSize()) throw new Error('Set an explicit page viewport');
    this.page = page;
    this.confirm = confirm;
    this.signal = signal;
  }

  point(x: number, y: number) {
    const viewport = this.page.viewportSize();
    if (!viewport || !(0 <= x && x < viewport.width && 0 <= y && y < viewport.height)) {
      throw new Error('Coordinates outside the browser viewport');
    }
  }

  async handle(call: ResponseComputerToolCall): Promise<ResponseInputItem.ComputerCallOutput> {
    if (call.pending_safety_checks.length) throw new Error('Computer use requires human safety review');
    if (!call.actions?.length || this.actions.length + call.actions.length > 64) throw new Error('Missing actions or action limit exceeded');
    for (const action of call.actions) {
      this.signal?.throwIfAborted();
      if (!await this.confirm(action)) throw new Error('Computer action refused');
      const modifiers = ('keys' in action ? action.keys ?? [] : []).map(key => keys[key.toUpperCase()] ?? key);
      if (action.type === 'keypress') {
        await this.page.keyboard.press(modifiers.join('+'));
      } else {
        const pressed: string[] = [];
        try {
          for (const key of modifiers) { await this.page.keyboard.down(key); pressed.push(key); }
          if (action.type === 'click' || action.type === 'double_click' || action.type === 'move' || action.type === 'scroll') {
            this.point(action.x, action.y);
            await this.page.mouse.move(action.x, action.y);
          }
          switch (action.type) {
            case 'click':
              if (action.button !== 'left' && action.button !== 'right' && action.button !== 'wheel') throw new Error('Unsupported mouse button');
              await this.page.mouse.click(action.x, action.y, { button: action.button === 'wheel' ? 'middle' : action.button });
              break;
            case 'double_click': await this.page.mouse.dblclick(action.x, action.y); break;
            case 'scroll': await this.page.mouse.wheel(action.scroll_x, action.scroll_y); break;
            case 'type':
              if (action.text.length > 10000) throw new Error('Text exceeds the example limit');
              await this.page.keyboard.insertText(action.text);
              break;
            case 'drag':
              if (action.path.length < 2 || action.path.length > 100) throw new Error('Drag path must contain 2 to 100 points');
              for (const point of action.path) this.point(point.x, point.y);
              await this.page.mouse.move(action.path[0].x, action.path[0].y);
              await this.page.mouse.down();
              try { for (const point of action.path.slice(1)) await this.page.mouse.move(point.x, point.y); }
              finally { await this.page.mouse.up(); }
              break;
            case 'wait': await sleep(1000, undefined, { signal: this.signal }); break;
            case 'screenshot': case 'move': break;
            default: throw new Error('Unsupported computer action');
          }
        } finally { for (const key of pressed.reverse()) await this.page.keyboard.up(key); }
      }
      this.actions.push(action.type);
    }
    const image = await this.page.screenshot({ type: 'png', scale: 'css' });
    const output = { type: 'computer_screenshot' as const, image_url: `data:image/png;base64,${image.toString('base64')}`, detail: 'original' };
    return { type: 'computer_call_output', call_id: call.call_id, output };
  }
}
