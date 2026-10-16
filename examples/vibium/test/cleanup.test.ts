import assert from 'node:assert/strict';
import { test, mock } from 'node:test';
import { browser } from 'vibium';
import { NativeDriver } from '../src/connection.ts';

test('cancelled native startup retains and stops its late client', { timeout: 3_000 }, async () => {
  let release!: (value: Awaited<ReturnType<typeof browser.start>>) => void;
  let stops = 0;
  const remote = { stop: async () => { stops++; } } as Awaited<ReturnType<typeof browser.start>>;
  const pending = new Promise<Awaited<ReturnType<typeof browser.start>>>(resolve => { release = resolve; });
  const start = mock.method(browser, 'start', () => pending);
  try {
    const driver = new NativeDriver();
    const controller = new AbortController();
    const operation = driver.connect('ws://127.0.0.1/owned', controller.signal);
    controller.abort();
    await assert.rejects(operation, /Browser task interrupted/);
    let cleaned = false;
    const closing = driver.close().then(() => { cleaned = true; });
    await new Promise(resolve => setTimeout(resolve, 10));
    assert.equal(cleaned, false, 'Cleanup must await the late native result');
    release(remote);
    await closing;
    assert.equal(stops, 1);
    assert.deepEqual(start.mock.calls[0].arguments, ['ws://127.0.0.1/owned', { headers: { Authorization: '' } }]);
  } finally { start.mock.restore(); }
});
