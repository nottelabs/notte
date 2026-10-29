import assert from 'node:assert/strict';
import { test } from 'node:test';
import { randomBytes } from 'node:crypto';
import { NotteClient, sessionStatus } from 'notte-sdk';
import { chromium, type Page } from 'playwright-core';
import { execute, perform, run } from './agent.ts';

const live = process.env.NOTTE_GEMINI_LIVE === '1';
const model = process.env.NOTTE_GEMINI_MODEL_LIVE === '1';

async function closed(id: string) {
  const client = new NotteClient();
  const signal = AbortSignal.timeout(15_000);
  while (!signal.aborted) {
    const response = await sessionStatus({ client: client.getClient(), path: { session_id: id }, throwOnError: true, signal });
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

test('A tab without a Playwright viewport uses the computer viewport', async () => {
  const clicks: number[][] = [];
  const page = { viewportSize: () => null, mouse: { click: async (x: number, y: number) => { clicks.push([x, y]); } } };
  await execute(page as unknown as Page, 'click', { x: 500, y: 250 });
  assert.deepEqual(clicks, [[720, 225]]);
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
      const point = async (selector: string, target = page) => {
        const box = (await target.locator(selector).boundingBox())!;
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
      assert.deepEqual(await destination.evaluate(() => [innerWidth, innerHeight]), [1440, 900]);
      await destination.setContent('<button onclick="document.title=\'Clicked\'">Popup</button>');
      await execute(destination, 'click', await point('button', destination));
      assert.equal(await destination.title(), 'Clicked');
    } finally { await browser.close(); }
  });
  await closed(id);
});

test('Delayed popup replans a stale action using the new tab screenshot', { skip: !live, timeout: 120_000 }, async () => {
  const original = globalThis.fetch, key = process.env.GEMINI_API_KEY, ids: string[] = [];
  let calls = 0, state: { text?: string; data?: string }[] = [];
  process.env.GEMINI_API_KEY = 'integration-test-not-a-real-key'; // pragma: allowlist secret
  globalThis.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    if (new URL(url).hostname === 'generativelanguage.googleapis.com') {
      calls++;
      if (calls === 2) await new Promise(resolve => setTimeout(resolve, 3000));
      if (calls === 3) {
        const request = input instanceof Request ? await input.clone().json() : JSON.parse(String(init?.body));
        state = request.input[0].result;
      }
      return Response.json({ id: `interaction-${calls}`, status: 'completed', steps: calls === 1
        ? [{ type: 'function_call', id: 'click-1', name: 'click', arguments: { x: 50, y: 50 } }]
        : calls === 2 ? [{ type: 'function_call', id: 'type-2', name: 'type', arguments: { text: 'stale' } }]
        : [{ type: 'model_output', content: [{ type: 'text', text: 'Done' }] }] });
    }
    const response = await original(input, init);
    if (new URL(url).pathname === '/sessions/start' && response.ok) ids.push((await response.clone().json()).session_id);
    return response;
  };
  try {
    const html = `<button style="position:absolute;left:20px;top:20px;width:100px;height:50px" onclick="setTimeout(()=>{const p=window.open('about:blank');p.document.write('<title>Popup</title><input autofocus oninput=&quot;document.title=String.fromCharCode(83,116,97,108,101)&quot;>');p.document.close()},2500)">Open</button>`;
    const result = await run('Open the new tab', 'data:text/html;base64,' + Buffer.from(html).toString('base64'));
    assert.equal(calls, 3);
    assert.match(state[0].text!, /not executed/);
    assert.ok(state[1].data);
    assert.equal(result.title, 'Popup');
    assert.equal(result.actions, 1);
    assert.deepEqual(ids, [result.session_id]);
  } finally {
    try { for (const id of ids) await closed(id); }
    finally {
      globalThis.fetch = original;
      if (key === undefined) delete process.env.GEMINI_API_KEY;
      else process.env.GEMINI_API_KEY = key;
    }
  }
});

test('Provider failure survives a browser close error and sanitizes the error', { skip: !live, timeout: 120_000 }, async t => {
  assert.ok(process.env.NOTTE_API_URL);
  const original = globalThis.fetch, key = process.env.GEMINI_API_KEY;
  const originalConnect = chromium.connectOverCDP.bind(chromium);
  t.mock.method(chromium, 'connectOverCDP', async (endpoint: string) => {
    const browser = await originalConnect(endpoint);
    const close = browser.close.bind(browser);
    browser.close = async () => {
      await close();
      throw new Error('Cleanup transport error https://private.invalid/credential');
    };
    return browser;
  });
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
      assert.match(error.message, /^Gemini API error 401/);
      assert.doesNotMatch(error.message, /https?:|wss?:|integration-test-not-a-real-key/);
      return true;
    });
    assert.equal(providerCalls, 1);
    assert.equal(ids.length, 1);
  } finally {
    try { for (const id of ids) await closed(id); }
    finally {
      globalThis.fetch = original;
      if (key === undefined) delete process.env.GEMINI_API_KEY;
      else process.env.GEMINI_API_KEY = key;
    }
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
    const nonce = randomBytes(4).toString('hex').toUpperCase();
    const html = `<title>Visual check</title><h1>Code: ${nonce}</h1><label>Code<input></label><button onclick="document.title='Saved '+document.querySelector('input').value">Save</button>`;
    const result = await run('Read the code shown on the page. Enter it in the Code field, then click Save.',
      'data:text/html;base64,' + Buffer.from(html).toString('base64'));
    assert.equal(result.title, `Saved ${nonce}`);
    assert.ok(result.actions > 0, 'The model must execute a browser action');
    assert.equal(ids.length, 1);
    assert.equal(result.session_id, ids[0]);
  } finally {
    try { for (const id of ids) { await closed(id); console.info(`Verified closed model session ${id}`); } }
    finally { globalThis.fetch = original; }
  }
});
