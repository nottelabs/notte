import assert from 'node:assert/strict';
import { after, mock, test } from 'node:test';
import { randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { Laminar } from '@lmnr-ai/lmnr';
import { InMemorySpanExporter, SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { NotteClient, sessionStatus } from 'notte-sdk';
import { chromium } from 'playwright-core';
import { readPage } from '../src/index.ts';

const live = process.env.NOTTE_LAMINAR_LIVE === '1';
const fakeCredential = 'notte-offline-test-credential'; // pragma: allowlist secret
if (!live) process.env.NOTTE_API_KEY = fakeCredential;
const exporter = new InMemorySpanExporter();
Laminar.initialize({
    projectApiKey: 'integration-test-not-a-real-key', // pragma: allowlist secret
    instrumentModules: {}, spanProcessor: new SimpleSpanProcessor(exporter),
});
after(async () => { await Laminar.shutdown(); });

async function offlineOwned<T>(operation: () => Promise<T>) {
  const id = randomUUID();
  let stopped = false, disconnected = false;
  const page = {
    title: async () => 'Example Domain',
    goto: async (url: string) => {
      if (url === 'http://127.0.0.1:1') throw new Error(`Browser error containing ${fakeCredential}`);
    },
  };
  const browser = { contexts: () => [{ newPage: async () => page }], close: async () => { disconnected = true; } };
  const session = { getId: () => id, cdpUrl: async () => `wss://example.invalid?api_key=${fakeCredential}` };
  const sessionMock = mock.method(NotteClient.prototype, 'Session', (() => ({
    use: async (run: (value: typeof session) => Promise<T>) => {
      try { return await run(session); }
      finally { stopped = true; }
    },
  })) as never);
  const connectionMock = mock.method(chromium, 'connectOverCDP', (async () => browser) as never);
  try { return { result: await operation(), ids: [id] }; }
  finally {
    sessionMock.mock.restore();
    connectionMock.mock.restore();
    assert.ok(stopped, 'The owned session was not stopped');
    assert.ok(disconnected, 'The browser was not disconnected');
  }
}

async function closed(id: string) {
  const client = new NotteClient();
  const signal = AbortSignal.timeout(15_000);
  while (!signal.aborted) {
    const response = await sessionStatus({ client: client.getClient(), path: { session_id: id }, throwOnError: true, signal });
    if (response.data.status === 'closed') return;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error('The owned browser session did not close');
}

async function owned<T>(operation: () => Promise<T>) {
  if (!live) return await offlineOwned(operation);
  assert.ok(process.env.NOTTE_API_URL, 'Choose the browser API explicitly');
  const original = globalThis.fetch, ids: string[] = [];
  globalThis.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const response = await original(input, init);
    if (new URL(url).pathname === '/sessions/start' && response.ok) ids.push((await response.clone().json()).session_id);
    return response;
  };
  let result: T;
  try { result = await operation(); }
  finally {
    try {
      for (const id of ids) await closed(id);
      assert.equal(ids.length, 1);
    } finally { globalThis.fetch = original; }
  }
  return { result, ids };
}

async function emitted(offset: number) {
  await Laminar.flush();
  const spans = exporter.getFinishedSpans().slice(offset).filter(span => span.name === 'notte.read_page');
  assert.equal(spans.length, 1);
  const payload = JSON.stringify({ attributes: spans[0].attributes, events: spans[0].events });
  assert.ok(process.env.NOTTE_API_KEY);
  for (const value of [process.env.NOTTE_API_KEY, fakeCredential, 'integration-test-not-a-real-key']) {
    assert.equal(payload.includes(value), false, 'Trace payload contained a credential');
  }
  return { span: spans[0], payload };
}

test('The browser result is traced and its owned session closes', { timeout: 120_000 }, async () => {
  const offset = exporter.getFinishedSpans().length;
  const { result, ids } = await owned(() => readPage());
  assert.equal(result.title, 'Example Domain');
  assert.deepEqual(ids, [result.session_id]);
  const { span, payload } = await emitted(offset);
  assert.equal(span.spanContext().traceId, result.trace_id);
  assert.notEqual(span.status.code, 2);
  assert.ok(payload.includes('Example Domain'));
  assert.ok(payload.includes(ids[0]));
});

test('Navigation failure is traced and its owned session closes', { timeout: 120_000 }, async () => {
  const offset = exporter.getFinishedSpans().length;
  await assert.rejects(owned(() => readPage('http://127.0.0.1:1')),
    /failed during navigation \(session [0-9a-f-]{36}, trace [0-9a-f]{32}\)/);
  const { span, payload } = await emitted(offset);
  assert.equal(span.status.code, 2);
  assert.ok(payload.includes('failed during navigation'));
});

test('A stalled disconnect cannot skip owner cleanup', { skip: !live, timeout: 45_000 }, async t => {
  const original = chromium.connectOverCDP.bind(chromium);
  let disconnected = 0, release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  t.mock.method(chromium, 'connectOverCDP', async (endpoint: string) => {
    const browser = await original(endpoint);
    const close = browser.close.bind(browser);
    t.mock.method(browser, 'close', async () => {
      await close();
      disconnected++;
      await gate;
    });
    return browser;
  });
  const offset = exporter.getFinishedSpans().length;
  const operation = owned(() => readPage()).then(() => undefined, error => error as Error);
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const failure = await Promise.race([
      operation,
      new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('Owned cleanup exceeded its deadline')), 20_000); }),
    ]);
    assert.ok(failure instanceof Error);
    assert.match(failure.message, /failed during reading the title \(session [0-9a-f-]{36}, trace [0-9a-f]{32}\)/);
    assert.equal(disconnected, 1);
    const { span, payload } = await emitted(offset);
    assert.equal(span.status.code, 2);
    assert.ok(payload.includes('failed during reading the title'));
  } finally {
    clearTimeout(timer);
    release();
    await operation;
  }
});

test('The exported trace is persisted in Laminar', {
  skip: !live || process.env.NOTTE_LAMINAR_EXPORT_LIVE !== '1', timeout: 200_000,
}, async () => {
  assert.ok(process.env.LMNR_PROJECT_API_KEY);
  let stdout: string;
  try {
    ({ stdout } = await promisify(execFile)(process.execPath,
      [fileURLToPath(new URL('../src/index.ts', import.meta.url))], { env: process.env, timeout: 150_000, maxBuffer: 2 * 1024 * 1024 }));
  } catch { throw new Error('Laminar CLI failed; child output withheld'); }
  const result = JSON.parse(stdout.trim().split(/\r?\n/).findLast(line => line.startsWith('{"title"'))!);
  await closed(result.session_id);
  const span = await persisted(result.trace_id);
  const output = typeof span.output === 'string' ? JSON.parse(span.output) : span.output;
  assert.equal(output.title, 'Example Domain');
  assert.equal(output.session_id, result.session_id);
});

test('A failed trace is persisted in Laminar', {
  skip: !live || process.env.NOTTE_LAMINAR_EXPORT_LIVE !== '1', timeout: 200_000,
}, async () => {
  let stderr = '';
  try {
    await promisify(execFile)(process.execPath,
      [fileURLToPath(new URL('../src/index.ts', import.meta.url)), 'http://127.0.0.1:1'],
      { env: process.env, timeout: 150_000, maxBuffer: 2 * 1024 * 1024 });
    assert.fail('Navigation unexpectedly succeeded');
  } catch (error) {
    stderr = String((error as { stderr?: string }).stderr ?? '');
  }
  const match = stderr.match(/failed during navigation \(session ([0-9a-f-]{36}), trace ([0-9a-f]{32})\)/);
  assert.ok(match, 'Child did not report the owned session and trace');
  await closed(match[1]);
  const span = await persisted(match[2]);
  const payload = JSON.stringify(span);
  assert.ok(payload.includes('failed during navigation'));
  assert.ok(payload.includes(match[1]));
  assert.equal(payload.includes(process.env.NOTTE_API_KEY!), false, 'Stored span contained a credential');
});

async function persisted(traceHex: string) {
  assert.match(traceHex, /^[0-9a-f]{32}$/);
  const traceId = traceHex.replace(/^(.{8})(.{4})(.{4})(.{4})(.{12})$/, '$1-$2-$3-$4-$5');
  const query = `SELECT * FROM spans WHERE trace_id = '${traceId}' LIMIT 5`;
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    const response = await fetch(`${(process.env.LMNR_BASE_URL ?? 'https://api.lmnr.ai').replace(/\/$/, '')}/v1/sql/query`, {
      method: 'POST', headers: { Authorization: `Bearer ${process.env.LMNR_PROJECT_API_KEY}`, 'content-type': 'application/json' },
      body: JSON.stringify({ query, parameters: {} }), signal: AbortSignal.timeout(Math.min(10_000, deadline - Date.now())),
    });
    assert.ok(response.ok, `Laminar query returned HTTP ${response.status}`);
    const rows = (await response.json()).data as { name: string; output: unknown }[];
    const row = rows.find(row => row.name === 'notte.read_page');
    if (row) {
      return row;
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error('The exported trace did not appear in Laminar');
}
