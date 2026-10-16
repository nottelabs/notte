import assert from 'node:assert/strict';
import { test } from 'node:test';
import { NotteClient, sessionStatus } from 'notte-sdk';
import { chromium, type Page } from 'playwright-core';
import { execute, perform, run } from './agent.ts';

const live = process.env.NOTTE_GEMINI_LIVE === '1';
const model = process.env.NOTTE_GEMINI_MODEL_LIVE === '1';

async function closed(id: string) {
  const client = new NotteClient();
  for (let attempt = 0; attempt < 30; attempt++) {
    const response = await sessionStatus({ client: client.getClient(), path: { session_id: id }, throwOnError: true, signal: AbortSignal.timeout(15_000) });
    if (response.data.status === 'closed') return;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  assert.fail('The browser session did not close');
}

test('Confirmation, blocked, and malformed safety decisions never touch the browser', async () => {
  for (const decision of ['require_confirmation', 'blocked', 'unknown', false]) {
    await assert.rejects(execute(undefined as unknown as Page, 'click', {
      safety_decision: typeof decision === 'string' ? { decision } : decision,
    }), /approval|blocked/);
  }
});

test('Browser actions fill a form and honor confirmation before clicking', { skip: !live, timeout: 120_000 }, async () => {
  assert.ok(process.env.NOTTE_API_URL, 'Choose the browser API explicitly');
  let id = '';
  await new NotteClient().Session({ max_duration_minutes: 3 }).use(async session => {
    id = session.getId()!;
    const browser = await chromium.connectOverCDP(await session.cdpUrl());
    try {
      const page = await browser.contexts()[0].newPage();
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.setContent('<input aria-label="Name"><button onclick="document.title=\'Saved \'+document.querySelector(\'input\').value">Save</button>');
      const point = async (selector: string) => {
        const box = (await page.locator(selector).boundingBox())!;
        return { x: Math.floor((box.x + box.width / 2) * 1000 / 1440), y: Math.floor((box.y + box.height / 2) * 1000 / 900) };
      };
      await execute(page, 'click', await point('input'));
      await execute(page, 'type', { text: 'Replace me' });
      await execute(page, 'hotkey', { keys: ['CTRL', 'A'] });
      await execute(page, 'type', { text: 'Ada' });
      assert.equal(await page.locator('input').inputValue(), 'Ada');
      const save = await point('button');
      await assert.rejects(execute(page, 'click', { ...save, safety_decision: { decision: 'require_confirmation' } }), /approval/);
      assert.equal(await page.title(), '');
      await execute(page, 'click', save);
      assert.equal(await page.title(), 'Saved Ada');
      await assert.rejects(execute(page, 'click', { x: 1000, y: 2 }), /coordinates/);
      await assert.rejects(execute(page, 'shell', {}), /Unsupported/);
      await page.setContent('<button onclick="window.open(\'about:blank\',\'_blank\').document.title=\'Popup\'">Open</button>');
      const destination = await perform(page, 'click', await point('button'));
      assert.notEqual(destination, page);
      assert.equal(await destination.title(), 'Popup');
    } finally { await browser.close(); }
  });
  await closed(id);
});

test('Provider failure closes the browser and sanitizes the error', { skip: !live, timeout: 120_000 }, async () => {
  assert.ok(process.env.NOTTE_API_URL);
  const original = globalThis.fetch, key = process.env.GEMINI_API_KEY;
  const ids: string[] = [];
  let providerCalls = 0;
  process.env.GEMINI_API_KEY = 'integration-test-not-a-real-key'; // pragma: allowlist secret
  globalThis.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    if (new URL(url).hostname === 'generativelanguage.googleapis.com') {
      providerCalls++;
      return Response.json({ error: { code: 401, message: 'Injected provider failure' } }, { status: 401 });
    }
    const response = await original(input, init);
    if (new URL(url).pathname === '/sessions/start' && response.ok) ids.push((await response.clone().json()).session_id);
    return response;
  };
  try {
    await assert.rejects(run('Read the page title'), (error: Error) => {
      assert.match(error.message, /^Gemini API error 401:/);
      assert.doesNotMatch(error.message, /https?:|wss?:|integration-test-not-a-real-key/);
      return true;
    });
    assert.equal(providerCalls, 1);
    assert.equal(ids.length, 1);
    await closed(ids[0]);
  } finally {
    globalThis.fetch = original;
    if (key === undefined) delete process.env.GEMINI_API_KEY;
    else process.env.GEMINI_API_KEY = key;
  }
});

test('Gemini drives the cloud browser and closes it on every outcome', { skip: !model, timeout: 180_000 }, async () => {
  assert.ok(process.env.GEMINI_API_KEY);
  assert.ok(process.env.NOTTE_API_URL);
  const original = globalThis.fetch, ids: string[] = [];
  globalThis.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const response = await original(input, init);
    if (new URL(url).pathname === '/sessions/start' && response.ok) ids.push((await response.clone().json()).session_id);
    return response;
  };
  try {
    const result = await run('Go to https://example.com and read its page title.');
    assert.equal(result.title, 'Example Domain');
    assert.ok(result.actions > 0, 'The model must execute a browser action');
    assert.equal(ids.length, 1);
    assert.equal(result.session_id, ids[0]);
  } finally {
    try { for (const id of ids) { await closed(id); console.info(`Verified closed model session ${id}`); } }
    finally { globalThis.fetch = original; }
  }
});
