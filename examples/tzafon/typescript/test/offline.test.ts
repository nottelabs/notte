import assert from 'node:assert/strict';
import { test } from 'node:test';
import Lightcone from '@tzafon/lightcone';
import type { ResponseComputerToolCall } from '@tzafon/lightcone/resources/responses';
import type { Page } from 'playwright-core';
import { NotteComputer, pixel, withBrowserDeadline } from '../src/computer.ts';
import { response, wire } from './fixture.ts';

function page() {
  const clicks: number[][] = [];
  const keys: string[][] = [];
  const fake = { viewportSize: () => ({ width: 1024, height: 768 }), screenshot: async () => Buffer.from('fixture-png'), mouse: { click: async (x: number, y: number) => { clicks.push([x, y]); } }, keyboard: { insertText: async (text: string) => { keys.push(['type', text]); }, press: async (key: string) => { keys.push(['press', key]); } } } as unknown as Page;
  return { fake, clicks, keys };
}
const provider = (fetch: typeof globalThis.fetch) => new Lightcone({ apiKey: 'fixture-provider-key', baseURL: 'https://lightcone.invalid', fetch, maxRetries: 0 }); // pragma: allowlist secret
const call = (safety = false) => response({ type: 'click', x: 160, y: 260, button: 'left' }, safety).output[0] as ResponseComputerToolCall;

test('disconnect rejection preserves the primary browser failure', async () => {
  const primary = new Error('Primary browser failure');
  await assert.rejects(withBrowserDeadline({ close: async () => { throw new Error('PRIVATE_CLOSE_FIXTURE'); } }, new AbortController().signal, async () => { throw primary; }), error => error === primary);
});

test('abort bounds a stalled disconnect and pending browser command', { timeout: 8_000 }, async () => {
  const controller = new AbortController();
  let closes = 0;
  const operation = withBrowserDeadline({ close: async () => { closes++; await new Promise<void>(() => {}); } }, controller.signal, () => new Promise<void>(() => {}));
  controller.abort();
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const result = await Promise.race([operation.then(() => false, () => true), new Promise<false>(resolve => { timer = setTimeout(() => resolve(false), 6_000); })]);
    assert.ok(result, 'Cancellation must finish despite a stalled disconnect');
    assert.equal(closes, 1, 'Only one native disconnect should be started');
  } finally { clearTimeout(timer); }
});

test('native wire replays history without persistence', async () => {
  const { mock, requests } = wire();
  const { fake, clicks, keys } = page();
  await new NotteComputer(fake, () => true, AbortSignal.timeout(1000)).run(provider(mock), 'fixture task');
  assert.deepEqual(clicks, [[163, 199]]);
  assert.deepEqual(keys, [['type', 'orbit-fixture'], ['press', 'Enter']]);
  assert.deepEqual(requests[1].input.slice(1).map((item: { type: string }) => item.type), ['computer_call', 'computer_call_output']);
  assert.equal(requests[1].input.at(-1).call_id, 'call_fixture_1');
});

test('eighth action can complete but ninth is refused', async () => {
  for (const complete of [true, false]) {
    const { mock, requests } = wire('limit');
    const fetch: typeof globalThis.fetch = async (...args) => {
      const result = await mock(...args);
      return complete && requests.length === 9 ? Response.json(response(null)) : result;
    };
    const computer = new NotteComputer(page().fake, () => true, AbortSignal.timeout(3000));
    if (complete) await computer.run(provider(fetch), 'fixture');
    else await assert.rejects(computer.run(provider(fetch), 'fixture'), /limit/);
    assert.equal(computer.actions.length, 8);
    assert.equal(requests.length, 9);
  }
});

test('safety and denied approval have no effects', async () => {
  for (const safety of [true, false]) {
    const { fake, clicks } = page();
    await assert.rejects(new NotteComputer(fake, () => safety, AbortSignal.timeout(1000)).handle(call(safety)));
    assert.deepEqual(clicks, []);
  }
});

test('invalid point_and_type text never clicks or types', async () => {
  for (const text of [null, 7, [], 'x'.repeat(1001)]) {
    const { fake, clicks, keys } = page();
    const computer = new NotteComputer(fake, () => true, new AbortController().signal);
    const command = response({ type: 'point_and_type', x: 160, y: 260, text }).output[0] as ResponseComputerToolCall;
    await assert.rejects(computer.handle(command), /Text exceeds the form limit/);
    assert.deepEqual(clicks, []);
    assert.deepEqual(keys, []);
    assert.deepEqual(computer.actions, []);
  }
});

test('cancelled approval never acts', async () => {
  const { fake, clicks } = page();
  const computer = new NotteComputer(fake, () => new Promise(() => {}), AbortSignal.timeout(20));
  // Keep the event loop alive until the unreferenced AbortSignal timer fires.
  const keepAlive = setTimeout(() => {}, 1000);
  try { await assert.rejects(computer.handle(call())); }
  finally { clearTimeout(keepAlive); }
  assert.deepEqual(clicks, []);
});

test('coordinate grid boundaries', () => {
  assert.deepEqual([pixel(0, 1024), pixel(500, 1024), pixel(999, 1024)], [0, 512, 1022]);
  for (const bad of [-1, 1000, NaN, Infinity, true, '500']) assert.throws(() => pixel(bad as number, 1024));
});


test('abort disconnects pending browser work before later effects', async () => {
  const { fake, keys } = page();
  let entered!: () => void;
  let finishClick!: () => void;
  const pending = new Promise<void>(resolve => { finishClick = resolve; });
  const clicking = new Promise<void>(resolve => { entered = resolve; });
  fake.mouse.click = async () => { entered(); await pending; };
  let closed = 0;
  const browser = { close: async () => { closed++; finishClick(); } };
  const controller = new AbortController();
  const computer = new NotteComputer(fake, () => true, controller.signal);
  const command = response({ type: 'point_and_type', x: 160, y: 260, text: 'must-not-type' }).output[0] as ResponseComputerToolCall;
  const operation = withBrowserDeadline(browser, controller.signal, () => computer.handle(command));
  await clicking;
  controller.abort();
  await assert.rejects(operation);
  assert.ok(closed >= 1);
  assert.deepEqual(keys, []);
  assert.deepEqual(computer.actions, []);
});
