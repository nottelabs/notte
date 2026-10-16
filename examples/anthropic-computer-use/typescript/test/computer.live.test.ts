import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { test } from 'node:test';
import { setTimeout as sleep } from 'node:timers/promises';
import Anthropic from '@anthropic-ai/sdk';
import type { BetaToolUseBlock } from '@anthropic-ai/sdk/resources/beta';
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';
import { NotteComputer } from '../src/computer.ts';
import { runDemo } from '../src/demo.ts';

const live = Boolean(process.env.NOTTE_API_KEY);
const tool = (name: string, input: Record<string, unknown> = {}): BetaToolUseBlock => ({
  id: `toolu_${name}`, type: 'tool_use', toolset_name: 'computer', name, input,
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

test('native tool protocol, real form actions, and permission refusal', { skip: !live, timeout: 90_000 }, async () => {
  const client = new NotteClient();
  const session = client.Session({ max_duration_minutes: 3 });
  try {
    await session.use(async () => {
      const browser = await chromium.connectOverCDP(await session.cdpUrl());
      try {
        const page = browser.contexts()[0].pages()[0];
        await page.goto('about:blank');
        await page.setViewportSize({ width: 1024, height: 768 });
        await page.setContent('<form onsubmit="event.preventDefault();document.querySelector(\'output\').textContent=\'Accepted\'"><input style="position:absolute;left:30px;top:30px;width:300px;height:40px"><output></output></form>');
        const computer = new NotteComputer(page, () => true);
        try {
          const shot = await computer.toolResult(tool('screenshot'));
          assert.equal(shot.toolset_name, 'computer');
          assert.ok(Array.isArray(shot.content) && shot.content[0].type === 'image');
          for (const call of [tool('left_click', { coordinate: [100, 50] }), tool('type', { text: 'native-protocol' }), tool('key', { text: 'Return' })]) {
            assert.ok(!(await computer.toolResult(call)).is_error, 'Native tool dispatch failed');
          }
          assert.equal(await page.locator('input').inputValue(), 'native-protocol');
          assert.equal(await page.locator('output').innerText(), 'Accepted');
          assert.ok((await computer.toolResult(tool('left_click', { coordinate: [1024, 0] }))).is_error);
          assert.ok((await computer.toolResult(tool('scroll', { direction: 'down', amount: 1 }))).is_error);
        } finally { await computer.close(); }
        const denied = new NotteComputer(page, () => false);
        try {
          assert.ok((await denied.toolResult(tool('type', { text: 'should-not-appear' }))).is_error);
          assert.equal(await page.locator('input').inputValue(), 'native-protocol');
        } finally { await denied.close(); }
      } finally { await browser.close(); }
    });
  } finally { if (session.getId()) await assertClosed(session.getId()!); }
});

test('unchanged demo closes its session after a real provider HTTP 401', { skip: !live, timeout: 90_000 }, async () => {
  let requests = 0;
  const server = createServer((request, response) => {
    requests++;
    request.resume();
    response.writeHead(401, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify({ type: 'error', error: { type: 'authentication_error', message: 'Test credential rejected' } }));
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const previous = { key: process.env.ANTHROPIC_API_KEY, url: process.env.ANTHROPIC_BASE_URL };
  const address = server.address();
  assert.ok(address && typeof address !== 'string');
  process.env.ANTHROPIC_API_KEY = 'test-invalid-key'; // pragma: allowlist secret
  process.env.ANTHROPIC_BASE_URL = `http://127.0.0.1:${address.port}`;
  try {
    let id: string | undefined;
    await assert.rejects(runDemo, (error: Error) => {
      id = /^Computer use failed: provider HTTP 401 \(session ([a-f0-9-]+)\)$/.exec(error.message)?.[1];
      assert.ok(error.cause instanceof Anthropic.AuthenticationError);
      return Boolean(id);
    });
    assert.ok(requests > 0, 'The actual provider request must reach the test server');
    await assertClosed(id!);
  } finally {
    for (const [name, value] of [['ANTHROPIC_API_KEY', previous.key], ['ANTHROPIC_BASE_URL', previous.url]]) {
      if (value === undefined) delete process.env[name!]; else process.env[name!] = value;
    }
    await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  }
});

test('unchanged demo completes a real model visual form task', { skip: !live || !process.env.ANTHROPIC_API_KEY, timeout: 180_000 }, async () => {
  let id: string | undefined;
  try {
    const result = await runDemo();
    id = result.session_id;
    assert.equal(result.output, 'Accepted');
    for (const name of ['screenshot', 'left_click', 'type', 'key']) assert.ok(result.calls.includes(name));
  } catch (error) {
    if (error instanceof Error) id = /session ([a-f0-9-]+)/.exec(error.message)?.[1];
    throw error;
  } finally { if (id) await assertClosed(id); }
});
