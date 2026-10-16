import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { test } from 'node:test';
import { setTimeout as sleep } from 'node:timers/promises';
import OpenAI from 'openai';
import type { ComputerAction, ResponseComputerToolCall } from 'openai/resources/responses/responses';
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';
import { NotteComputer } from '../src/computer.ts';
import { runDemo } from '../src/demo.ts';

const live = Boolean(process.env.NOTTE_API_KEY);
const call = (...actions: ComputerAction[]): ResponseComputerToolCall => ({
  id: 'cu_test', call_id: 'call_test', type: 'computer_call', status: 'completed', actions, pending_safety_checks: [],
});

async function assertClosed(id: string) {
  const deadline = Date.now() + 15_000;
  while (true) {
    const response = await fetch(`${process.env.NOTTE_API_URL ?? 'https://api.notte.cc'}/sessions/${id}`, {
      headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` }, signal: AbortSignal.timeout(15_000),
    });
    assert.equal(response.status, 200, 'Authoritative session lookup failed');
    const { status } = await response.json() as { status: string };
    if (status === 'closed') return;
    assert.equal(status, 'active', 'Unexpected terminal session state');
    assert.ok(Date.now() < deadline, `Owned session ${id} remained active`);
    await sleep(500);
  }
}

test('batched native actions, exact screenshot size, and permission refusal', { skip: !live, timeout: 90_000 }, async () => {
  const session = new NotteClient().Session({ max_duration_minutes: 3 });
  let id: string | undefined;
  try {
    await session.use(async () => {
      id = session.getId()!;
      const browser = await chromium.connectOverCDP(await session.cdpUrl());
      try {
        const page = browser.contexts()[0].pages()[0];
        await page.goto('about:blank');
        await page.setViewportSize({ width: 1024, height: 768 });
        await page.setContent('<form onsubmit="event.preventDefault();document.querySelector(\'output\').textContent=\'Accepted\'"><input style="position:absolute;left:30px;top:30px;width:300px;height:40px"><output></output></form>');
        const computer = new NotteComputer(page, () => true);
        const result = await computer.handle(call(
          { type: 'screenshot' }, { type: 'click', button: 'left', x: 100, y: 50 },
          { type: 'type', text: 'native-protocol' }, { type: 'keypress', keys: ['ENTER'] },
        ));
        assert.equal(result.type, 'computer_call_output');
        assert.equal(result.call_id, 'call_test');
        const image = Buffer.from(result.output.image_url!.split(',')[1], 'base64');
        assert.equal(image.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
        assert.equal(image.readUInt32BE(16), 1024);
        assert.equal(image.readUInt32BE(20), 768);
        assert.equal(await page.locator('input').inputValue(), 'native-protocol');
        assert.equal(await page.locator('output').innerText(), 'Accepted');
        await computer.handle(call(
          { type: 'move', x: 20, y: 200 }, { type: 'double_click', x: 100, y: 50, keys: [] },
          { type: 'scroll', x: 20, y: 200, scroll_x: 0, scroll_y: 100 },
          { type: 'drag', path: [{ x: 100, y: 50 }, { x: 120, y: 50 }] }, { type: 'wait' },
        ));
        assert.equal(new Set(computer.actions).size, 9);
        await assert.rejects(() => computer.handle(call({ type: 'click', button: 'left', x: 1024, y: 0 })), /Coordinates outside/);
        const unsafe = call({ type: 'type', text: 'denied' });
        unsafe.pending_safety_checks = [{ id: 'check_1', code: 'unsafe', message: 'Review required' }];
        await assert.rejects(() => computer.handle(unsafe), /human safety review/);
        await assert.rejects(() => new NotteComputer(page, () => false).handle(call({ type: 'type', text: 'denied' })), /refused/);
        assert.equal(await page.locator('input').inputValue(), 'native-protocol');
      } finally { await browser.close(); }
    });
  } finally { if (id) await assertClosed(id); }
});

test('unchanged demo closes its browser after actual provider HTTP 401', { skip: !live, timeout: 90_000 }, async () => {
  const payloads: { tools: unknown; previous_response_id?: string; input: { call_id: string; output: { detail: string; image_url: string } }[] }[] = [];
  const server = createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    payloads.push(JSON.parse(Buffer.concat(chunks).toString()));
    response.writeHead(payloads.length === 1 ? 200 : 401, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify(payloads.length === 1
      ? { id: 'resp_protocol', object: 'response', created_at: 0, model: 'gpt-6.1-sol', status: 'completed', output: [call({ type: 'screenshot' })] }
      : { error: { type: 'invalid_request_error', message: 'Test credential rejected', code: 'invalid_api_key' } }));
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const previous = { key: process.env.OPENAI_API_KEY, url: process.env.OPENAI_BASE_URL };
  const address = server.address();
  assert.ok(address && typeof address !== 'string');
  process.env.OPENAI_API_KEY = 'test-invalid-key'; // pragma: allowlist secret
  process.env.OPENAI_BASE_URL = `http://127.0.0.1:${address.port}`;
  try {
    let id: string | undefined;
    await assert.rejects(runDemo, (error: Error) => {
      id = /^Computer use failed: provider HTTP 401 \(session ([a-f0-9-]+)\)$/.exec(error.message)?.[1];
      assert.ok(error.cause instanceof OpenAI.AuthenticationError);
      return Boolean(id);
    });
    assert.equal(payloads.length, 2, 'The unchanged demo must complete a screenshot turn before the real HTTP401');
    assert.deepEqual(payloads[0].tools, [{ type: 'computer' }]);
    assert.equal(payloads[1].previous_response_id, 'resp_protocol');
    assert.equal(payloads[1].input[0].call_id, 'call_test');
    assert.equal(payloads[1].input[0].output.detail, 'original');
    assert.ok(payloads[1].input[0].output.image_url.startsWith('data:image/png;base64,'));
    await assertClosed(id!);
  } finally {
    for (const [name, value] of [['OPENAI_API_KEY', previous.key], ['OPENAI_BASE_URL', previous.url]]) {
      if (value === undefined) delete process.env[name!]; else process.env[name!] = value;
    }
    await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  }
});

test('unchanged demo completes a real model visual form task', { skip: !live || !process.env.OPENAI_API_KEY, timeout: 180_000 }, async () => {
  let id: string | undefined;
  try {
    const result = await runDemo();
    id = result.session_id;
    assert.equal(result.output, 'Accepted');
    assert.ok(result.actions.includes('type'));
    assert.ok(result.actions.includes('keypress') || result.actions.includes('click'));
  } catch (error) {
    if (error instanceof Error) id = /session ([a-f0-9-]+)/.exec(error.message)?.[1];
    throw error;
  } finally { if (id) await assertClosed(id); }
});
