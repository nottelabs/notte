import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { appendFileSync } from 'node:fs';
import { once } from 'node:events';
import { test, mock } from 'node:test';
import { inspect } from 'node:util';
import { setTimeout as sleep } from 'node:timers/promises';
import OpenAI from 'openai';
import type { ComputerAction, ResponseComputerToolCall } from 'openai/resources/responses/responses';
import { NotteClient } from 'notte-sdk';
import { chromium, type Browser, type Page } from 'playwright-core';
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
    if (status === 'closed') {
      if (process.env.CUA_OWNERSHIP_JOURNAL) appendFileSync(process.env.CUA_OWNERSHIP_JOURNAL, JSON.stringify({ event: 'independent_get_closed', session_id: id }) + '\n', { mode: 0o600 });
      return;
    }
    assert.equal(status, 'active', 'Unexpected terminal session state');
    assert.ok(Date.now() < deadline, `Owned session ${id} remained active`);
    await sleep(500);
  }
}

test('cancellation releases a stalled screenshot to its browser owner', { timeout: 5000 }, async () => {
  const controller = new AbortController();
  let entered!: () => void;
  const started = new Promise<void>(resolve => { entered = resolve; });
  let release!: (image: Buffer) => void;
  const screenshot = new Promise<Buffer>(resolve => { release = resolve; });
  const page = {
    viewportSize: () => ({ width: 1024, height: 768 }),
    screenshot: () => { entered(); return screenshot; },
  } as unknown as Page;
  const operation = new NotteComputer(page, () => true, controller.signal).handle(call({ type: 'screenshot' }));
  const settled = operation.then(() => 'completed', error => error);
  try {
    await started;
    const reason = new Error('Computer task cancelled');
    controller.abort(reason);
    const outcome = await Promise.race([settled, sleep(100).then(() => 'still waiting')]);
    assert.equal(outcome, reason, 'The owner must regain control before a stalled screenshot finishes');
  } finally {
    release(Buffer.alloc(0));
    await settled;
  }
});

for (const metadata of ['omitted', 'null', 'empty', 'pending'] as const) {
  test(`native Responses client handles ${metadata} safety metadata`, async () => {
    const { pending_safety_checks: _checks, ...withoutChecks } = call({ type: 'screenshot' });
    const computerCall = metadata === 'omitted' ? withoutChecks : {
      ...withoutChecks, pending_safety_checks: metadata === 'null' ? null : metadata === 'pending'
        ? [{ id: 'check_1', code: 'unsafe', message: 'Review required' }] : [],
    };
    const server = createServer((request, response) => {
      request.resume();
      response.writeHead(200, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({
        id: 'resp_metadata', object: 'response', created_at: 0, model: 'gpt-6.1-sol', status: 'completed', output: [computerCall],
      }));
    });
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    const address = server.address();
    assert.ok(address && typeof address !== 'string');
    try {
      const provider = new OpenAI({ apiKey: 'fixture-local-only', baseURL: `http://127.0.0.1:${address.port}`, maxRetries: 0 }); // pragma: allowlist secret
      const response = await provider.responses.create({ model: 'gpt-6.1-sol', tools: [{ type: 'computer' }], input: 'Check the fixture' });
      const nativeCall = response.output.find(item => item.type === 'computer_call');
      assert.ok(nativeCall);
      let screenshots = 0;
      const page = {
        viewportSize: () => ({ width: 1024, height: 768 }),
        screenshot: async () => { screenshots++; return Buffer.alloc(0); },
      } as unknown as Page;
      const operation = new NotteComputer(page, () => true).handle(nativeCall);
      if (metadata === 'pending') {
        await assert.rejects(operation, /human safety review/);
        assert.equal(screenshots, 0);
      } else {
        assert.equal((await operation).call_id, 'call_test');
        assert.equal(screenshots, 1);
      }
    } finally {
      await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
    }
  });
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
        assert.deepEqual(image.subarray(0, 8), Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
        assert.equal(image.readUInt32BE(16), 1024);
        assert.equal(image.readUInt32BE(20), 768);
        assert.equal(await page.locator('input').inputValue(), 'native-protocol');
        assert.equal(await page.locator('output').innerText(), 'Accepted');
        await assert.rejects(() => computer.handle(call({ type: 'click', button: 'left', x: 1024, y: 0 })), /Coordinates outside/);
        const unsafe = call({ type: 'type', text: 'denied' });
        unsafe.pending_safety_checks = [{ id: 'check_1', code: 'unsafe', message: 'Review required' }];
        await assert.rejects(() => computer.handle(unsafe), /human safety review/);
        await assert.rejects(() => new NotteComputer(page, () => false).handle(call({ type: 'type', text: 'denied' })), /refused/);
        assert.equal(await page.locator('input').inputValue(), 'native-protocol');
        for (const never of [false, true]) {
          const controller = new AbortController();
          let approve!: (value: boolean) => void;
          const waiting = new NotteComputer(page, () => new Promise<boolean>(resolve => { approve = resolve; }), controller.signal);
          const result = waiting.handle(call({ type: 'type', text: 'late input' }));
          await sleep(10);
          controller.abort(new Error('Approval cancelled'));
          if (!never) approve(true);
          await assert.rejects(result, /Approval cancelled/);
          assert.equal(await page.locator('input').inputValue(), 'native-protocol');
        }
        await page.setContent(await readFile(new URL('../../fixtures/mouse.html', import.meta.url), 'utf8'));
        await computer.handle(call({ type: 'move', x: 400, y: 100 }));
        assert.equal(await page.locator('#pad').getAttribute('data-position'), '400,100');
        await computer.handle(call({ type: 'double_click', x: 400, y: 100, keys: [] }));
        assert.equal(await page.locator('#pad').getAttribute('data-double-click'), 'yes');
        await computer.handle(call({ type: 'click', button: 'left', x: 400, y: 100, keys: ['SHIFT'] }));
        assert.equal(await page.locator('#pad').getAttribute('data-shift'), 'true');
        await computer.handle(call({ type: 'click', button: 'left', x: 400, y: 100 }));
        assert.equal(await page.locator('#pad').getAttribute('data-shift'), 'false');
        await computer.handle(call({ type: 'drag', path: [{ x: 100, y: 350 }, { x: 200, y: 350 }] }));
        assert.equal(await page.locator('#drag').getAttribute('data-position'), '200,350');
        await computer.handle(call({ type: 'scroll', x: 800, y: 600, scroll_x: 0, scroll_y: 200 }, { type: 'wait' }));
        assert.ok(await page.evaluate(() => window.scrollY) > 0);
        assert.equal(new Set(computer.actions).size, 9);
        for (const extraCall of [false, true]) {
          let requests = 0;
          const server = createServer((request, response) => {
            request.resume();
            requests++;
            response.writeHead(200, { 'Content-Type': 'application/json' });
            response.end(JSON.stringify({
              id: `resp_${requests}`, object: 'response', created_at: 0, model: 'gpt-6.1-sol', status: 'completed',
              output: requests === 9 && !extraCall ? [] : [call({ type: 'screenshot' })],
            }));
          });
          server.listen(0, '127.0.0.1');
          await once(server, 'listening');
          const address = server.address();
          assert.ok(address && typeof address !== 'string');
          try {
            const provider = new OpenAI({ apiKey: 'test-invalid-key', baseURL: `http://127.0.0.1:${address.port}`, maxRetries: 0 }); // pragma: allowlist secret
            const limited = new NotteComputer(page, () => true);
            if (extraCall) await assert.rejects(() => limited.run(provider, 'Check the screenshot'), /turn limit exceeded/);
            else await limited.run(provider, 'Check the screenshot');
            assert.equal(limited.actions.length, 8);
            assert.equal(requests, 9);
          } finally {
            await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
          }
        }
      } finally { await browser.close(); }
    });
  } finally { if (id) await assertClosed(id); }
});

for (const closeMode of ['normal', 'reject', 'timeout'] as const) for (const cancelScreenshot of [false, true]) {
  const failureMode = cancelScreenshot ? 'cancels a stalled screenshot' : 'preserves private HTTP 401';
  test(`unchanged demo ${failureMode} and closes ownership (${closeMode})`, { skip: !live, timeout: 90_000 }, async () => {
    const payloads: { model: string; store: boolean; provider: { allow_fallbacks: boolean }; tools: unknown; previous_response_id?: string; input: { type: string; call_id: string; output: { detail: string; image_url: string } }[] }[] = [];
    const server = createServer(async (request, response) => {
      const chunks = [];
      for await (const chunk of request) chunks.push(chunk);
      payloads.push(JSON.parse(Buffer.concat(chunks).toString()));
      response.writeHead(payloads.length === 1 ? 200 : 401, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify(payloads.length === 1
        ? { id: 'resp_protocol', object: 'response', created_at: 0, model: 'gpt-6.1-sol', status: 'completed', output: [call({ type: 'screenshot' })] }
        : { error: { type: 'invalid_request_error', message: 'private-provider-body-fixture', code: 'invalid_api_key' } }));
    });
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    const previous = { key: process.env.OPENROUTER_API_KEY, url: process.env.OPENAI_BASE_URL };
    const address = server.address();
    assert.ok(address && typeof address !== 'string');
    process.env.OPENROUTER_API_KEY = 'test-invalid-key'; // pragma: allowlist secret
    process.env.OPENAI_BASE_URL = `http://127.0.0.1:${address.port}`;
    let id: string | undefined;
    let restoreStart: (() => void) | undefined;
    let failure: unknown;
    let nativeBrowser: Browser | undefined;
    let restoreClose: (() => void) | undefined;
    let restoreScreenshot: (() => void) | undefined;
    let releaseScreenshot: ((image: Buffer) => void) | undefined;
    let screenshotStarted = false;
    const controller = new AbortController();
    const timeout = AbortSignal.timeout.bind(AbortSignal);
    const deadline = cancelScreenshot ? mock.method(AbortSignal, 'timeout', (milliseconds: number) =>
      milliseconds === 120_000 ? controller.signal : timeout(milliseconds)) : undefined;
    const messages: string[] = [];
    const sessionFactory = NotteClient.prototype.Session;
    const owner = mock.method(NotteClient.prototype, 'Session', function (this: NotteClient, ...args: Parameters<NotteClient['Session']>) {
      const session = sessionFactory.apply(this, args);
      const start = session.start.bind(session);
      const starting = mock.method(session, 'start', async (...options: Parameters<typeof start>) => {
        const result = await start(...options);
        id = session.getId() ?? undefined;
        if (process.env.CUA_OWNERSHIP_JOURNAL) appendFileSync(process.env.CUA_OWNERSHIP_JOURNAL, JSON.stringify({ event: 'allocated', session_id: id }) + '\n', { mode: 0o600 });
        return result;
      });
      restoreStart = () => starting.mock.restore();
      return session;
    });
    const connect = chromium.connectOverCDP.bind(chromium);
    const transport = mock.method(chromium, 'connectOverCDP', async (...args: Parameters<typeof connect>) => {
      nativeBrowser = await connect(...args);
      if (cancelScreenshot) {
        const page = nativeBrowser.contexts()[0].pages()[0];
        const screenshot = page.screenshot.bind(page);
        const capture = mock.method(page, 'screenshot', async (...options: Parameters<typeof screenshot>) => {
          await screenshot(...options);
          screenshotStarted = true;
          const stalled = new Promise<Buffer>(resolve => { releaseScreenshot = resolve; });
          controller.abort(new DOMException('Computer task deadline', 'TimeoutError'));
          return stalled;
        });
        restoreScreenshot = () => capture.mock.restore();
      }
      if (closeMode !== 'normal') {
        const closing = mock.method(nativeBrowser, 'close', async () => {
          if (closeMode === 'timeout') await new Promise<void>(() => {});
          throw new Error('private-close-body-fixture');
        });
        restoreClose = () => closing.mock.restore();
      }
      return nativeBrowser;
    });
    const warning = mock.method(console, 'warn', (...args: unknown[]) => { messages.push(inspect(args)); });
    try {
      try { await runDemo(); }
      catch (error) { failure = error; }
    } finally {
      try {
        if (id) {
          let closed = false;
          try { await assertClosed(id); closed = true; }
          finally {
            if (!closed) {
              const response = await fetch(`${process.env.NOTTE_API_URL ?? 'https://api.notte.cc'}/sessions/${id}/stop`, {
                method: 'DELETE', headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY}` },
                signal: AbortSignal.timeout(15_000), redirect: 'error',
              });
              assert.ok(response.ok, 'Fallback stop failed for the owned browser');
              await assertClosed(id);
            }
          }
        }
      } finally {
        releaseScreenshot?.(Buffer.alloc(0));
        restoreScreenshot?.();
        deadline?.mock.restore();
        restoreClose?.();
        transport.mock.restore();
        restoreStart?.();
        owner.mock.restore();
        warning.mock.restore();
        try {
          if (nativeBrowser) await Promise.race([
            nativeBrowser.close(),
            sleep(5000, undefined, { ref: false }).then(() => { throw new Error('Test transport cleanup timed out'); }),
          ]);
        } finally {
          for (const [name, value] of [['OPENROUTER_API_KEY', previous.key], ['OPENAI_BASE_URL', previous.url]]) {
            if (value === undefined) delete process.env[name!]; else process.env[name!] = value;
          }
          await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
        }
      }
    }
    assert.ok(id, 'The unchanged recipe must allocate an independently tracked browser');
    assert.ok(failure instanceof Error);
    assert.match(failure.message, cancelScreenshot
      ? /^Computer use failed: timeout \(session [a-f0-9-]+\)$/
      : /^Computer use failed: provider HTTP 401 \(session [a-f0-9-]+\)$/);
    assert.equal(failure.cause, undefined);
    const rendered = inspect(failure, { depth: 10 }) + failure.stack + messages.join('\n');
    assert.ok(!rendered.includes('private-provider-body-fixture'));
    assert.ok(!rendered.includes('private-close-body-fixture'));
    assert.equal(payloads.length, cancelScreenshot ? 1 : 2);
    assert.deepEqual(payloads[0].tools, [{ type: 'computer' }]);
    if (cancelScreenshot) {
      assert.ok(screenshotStarted, 'Cancellation must follow an actual native browser screenshot');
      return;
    }
    assert.equal(payloads[0].model, 'openai/gpt-6.1-sol');
    for (const payload of payloads) {
      assert.equal('previous_response_id' in payload, false);
      assert.equal(payload.store, false);
      assert.deepEqual(payload.provider, { allow_fallbacks: false });
    }
    assert.deepEqual(payloads[1].input[0], payloads[0].input[0]);
    assert.equal(payloads[1].input[1].type, 'computer_call');
    assert.equal(payloads[1].input[2].call_id, 'call_test');
    assert.equal(payloads[1].input[2].output.detail, 'original');
    assert.ok(payloads[1].input[2].output.image_url.startsWith('data:image/png;base64,'));
  });
}

test('unchanged demo completes a real model visual form task', { skip: !live || !process.env.OPENROUTER_API_KEY, timeout: 180_000 }, async () => {
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
