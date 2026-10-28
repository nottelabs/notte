import assert from 'node:assert/strict';
import { test } from 'node:test';
import { setTimeout } from 'node:timers/promises';
import { NotteClient, sessionStatus } from 'notte-sdk';
import { chromium } from 'playwright-core';
import { readPage } from '../src/trigger/read-page.ts';

const live = process.env.NOTTE_TRIGGER_LIVE === '1';

async function closed(sessionId: string) {
  const client = new NotteClient();
  const signal = AbortSignal.timeout(15_000);
  while (!signal.aborted) {
    const response = await sessionStatus({
      client: client.getClient(), path: { session_id: sessionId }, throwOnError: true,
      signal,
    });
    if (response.data.status === 'closed') return;
    await setTimeout(500);
  }
  assert.fail('The owned browser did not close');
}

async function trackSessions(run: () => Promise<void>) {
  const original = globalThis.fetch;
  const ids: string[] = [];
  globalThis.fetch = async (input, options) => {
    const response = await original(input, options);
    const url = new URL(input instanceof Request ? input.url : String(input));
    if (url.pathname === '/sessions/start' && response.ok) {
      const body = await response.clone().json() as { session_id: string };
      ids.push(body.session_id);
    }
    return response;
  };
  try {
    await run();
  } finally {
    globalThis.fetch = original;
    assert.equal(ids.length, 1, 'The task should create exactly one owned browser');
    await closed(ids[0]);
  }
}

test('Trigger task browser handler', { skip: !live, timeout: 120_000 }, async (t) => {
  assert.ok(process.env.NOTTE_API_KEY);
  assert.ok(process.env.NOTTE_API_URL, 'Choose the test API explicitly');
  const fixtureUrl = 'https://trigger-fixture.notte.test/read';
  const connect = chromium.connectOverCDP.bind(chromium);
  let fixtureRequests = 0;
  t.mock.method(chromium, 'connectOverCDP', async (...args: Parameters<typeof chromium.connectOverCDP>) => {
    const browser = await connect(...args);
    await browser.contexts()[0].route(fixtureUrl, route => {
      fixtureRequests++;
      return route.fulfill({
        status: 200,
        contentType: 'text/html',
        body: '<!doctype html><title>Trigger fixture</title><h1>Owned browser fixture</h1>',
      });
    });
    return browser;
  });
  await t.test('reads the page and closes its browser', () => trackSessions(async () => {
    const result = await readPage({ url: fixtureUrl });
    assert.equal(result.title, 'Trigger fixture');
    assert.ok(result.session_id);
    assert.equal(fixtureRequests, 1, 'The real browser must read the intercepted fixture');
  }));
  await t.test('closes its browser when navigation fails', () => trackSessions(async () => {
    await assert.rejects(readPage({ url: 'https://missing.notte.invalid' }), /Notte browser task failed during navigation/);
  }));
});
