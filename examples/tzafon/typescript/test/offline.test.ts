import assert from 'node:assert/strict';
import { test } from 'node:test';
import Lightcone from '@tzafon/lightcone';
import type { ResponseComputerToolCall } from '@tzafon/lightcone/resources/responses';
import type { Page } from 'playwright-core';
import { NotteComputer, pixel } from '../src/computer.ts';
import { response, wire } from './fixture.ts';

function page() {
  const clicks: number[][] = [];
  const keys: string[][] = [];
  const fake = { viewportSize: () => ({ width: 1024, height: 768 }), screenshot: async () => Buffer.from('fixture-png'), mouse: { click: async (x: number, y: number) => { clicks.push([x, y]); } }, keyboard: { insertText: async (text: string) => { keys.push(['type', text]); }, press: async (key: string) => { keys.push(['press', key]); } } } as unknown as Page;
  return { fake, clicks, keys };
}
const provider = (fetch: typeof globalThis.fetch) => new Lightcone({ apiKey: 'fixture-provider-key', baseURL: 'https://lightcone.invalid', fetch, maxRetries: 0 }); // pragma: allowlist secret
const call = (safety = false) => response({ type: 'click', x: 160, y: 260, button: 'left' }, safety).output[0] as ResponseComputerToolCall;

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
