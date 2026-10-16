import { spawn, type ChildProcess } from 'node:child_process';
import { access } from 'node:fs/promises';
import { constants } from 'node:fs';
import { once } from 'node:events';
import { createServer } from 'node:net';
import { NotteClient } from 'notte-sdk';
import { browser } from 'vibium';
import { cdpBridge } from './bridge.ts';

type Remote = Awaited<ReturnType<typeof browser.start>>;

export function interrupted<T>(operation: Promise<T>, signal: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    const abort = () => reject(new Error('Browser task interrupted'));
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
    operation.then(resolve, reject).finally(() => signal.removeEventListener('abort', abort));
  });
}

async function freePort() {
  const listener = createServer();
  listener.listen(0, '127.0.0.1');
  await once(listener, 'listening');
  const address = listener.address();
  if (!address || typeof address === 'string') throw new Error('Could not bind ChromeDriver');
  await new Promise<void>((resolve, reject) => listener.close(error => error ? reject(error) : resolve()));
  return address.port;
}

export class NativeDriver {
  private process?: ChildProcess;
  private base = '';
  private nativeId?: string;
  private starts: Promise<Remote>[] = [];
  private stopped = new Set<Remote>();
  private closing?: Promise<void>;

  async start(signal: AbortSignal) {
    const path = process.env.CHROMEDRIVER_PATH;
    if (!path) throw new Error('Set CHROMEDRIVER_PATH to a matching ChromeDriver binary');
    await access(path, constants.X_OK);
    signal.throwIfAborted();
    const port = await freePort();
    this.process = spawn(path, [`--port=${port}`, '--log-level=OFF'], { stdio: 'ignore', detached: true });
    this.process.on('error', () => {});
    this.base = `http://127.0.0.1:${port}`;
    for (let attempt = 0; attempt < 50; attempt++) {
      signal.throwIfAborted();
      if (this.process.exitCode !== null) throw new Error('ChromeDriver exited during startup');
      try {
        if ((await fetch(`${this.base}/status`, { signal: AbortSignal.timeout(500) })).ok) return;
      } catch { /* The owned listener may still be starting. */ }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error('ChromeDriver did not start');
  }

  private async request(path: string, init: RequestInit = {}, signal?: AbortSignal) {
    return fetch(`${this.base}${path}`, { ...init, redirect: 'error',
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.any([AbortSignal.timeout(20_000), ...(signal ? [signal] : [])]),
    });
  }

  async attach(address: string, signal: AbortSignal) {
    const response = await this.request('/session', { method: 'POST', body: JSON.stringify({ capabilities: { alwaysMatch: {
      browserName: 'chrome', webSocketUrl: true,
      'goog:chromeOptions': { debuggerAddress: address, windowTypes: ['page', 'tab', 'other'] },
    } } }) }, signal);
    const value = (await response.json() as { value?: { sessionId?: string; capabilities?: { webSocketUrl?: string } } }).value;
    this.nativeId = value?.sessionId;
    if (!response.ok || !this.nativeId || !value?.capabilities?.webSocketUrl) {
      throw new Error('Native BiDi attachment is unavailable for this Notte session');
    }
    const url = new URL(value.capabilities.webSocketUrl);
    if (url.protocol !== 'ws:' || url.hostname !== '127.0.0.1') throw new Error('ChromeDriver returned a non-local BiDi URL');
    return url.href;
  }

  connect(url: string, signal: AbortSignal) {
    signal.throwIfAborted();
    // Only the owned loopback URL reaches native client arguments; override ambient auth.
    const start = browser.start(url, { headers: { Authorization: '' } });
    this.starts.push(start);
    return interrupted(start, signal);
  }

  async disconnect(remote: Remote) {
    await interrupted(remote.stop(), AbortSignal.timeout(70_000));
    this.stopped.add(remote);
  }

  close() {
    return this.closing ??= this.closeOwned();
  }

  private async closeOwned() {
    let failed = false;
    try {
      // Notte has already stopped before local clients are reaped. Pinned SDK
      // native readiness has two attempts with a 60-second deadline per attempt.
      for (const start of this.starts) {
        try {
          const remote = await interrupted(start, AbortSignal.timeout(125_000));
          if (!this.stopped.has(remote)) await this.disconnect(remote);
        } catch { failed = true; }
      }
      if (this.nativeId) {
        try { if (!(await this.request(`/session/${this.nativeId}`, { method: 'DELETE' })).ok) failed = true; }
        catch { failed = true; }
      }
    } finally {
      const child = this.process;
      if (child?.pid && child.exitCode === null && child.signalCode === null) {
        const exited = once(child, 'exit');
        try { process.kill(-child.pid, 'SIGTERM'); } catch { /* Already stopped. */ }
        try { await interrupted(exited, AbortSignal.timeout(3_000)); }
        catch {
          try { process.kill(-child.pid, 'SIGKILL'); } catch { /* Already stopped. */ }
          await interrupted(exited, AbortSignal.timeout(3_000));
        }
      }
    }
    if (failed) throw new Error('Native client cleanup failed');
  }
}

export async function withNotteVibium<T>(
  task: (driver: NativeDriver, bidiUrl: string, sessionId: string, signal: AbortSignal) => Promise<T>,
  options: { signal?: AbortSignal; client?: NotteClient } = {},
) {
  const signal = AbortSignal.any([AbortSignal.timeout(90_000), ...(options.signal ? [options.signal] : [])]);
  const driver = new NativeDriver();
  let sessionId = 'unallocated';
  let failed = false;
  try {
    await driver.start(signal);
    return await (options.client ?? new NotteClient()).Session({ max_duration_minutes: 3, proxies: false, browser_type: 'chrome' }).use(async session => {
      sessionId = session.getId()!;
      try {
        signal.throwIfAborted();
        const bridge = await cdpBridge(await session.cdpUrl(), signal);
        try {
          const url = await driver.attach(bridge.address, signal);
          return await interrupted(task(driver, url, sessionId, signal), signal);
        } finally { await bridge.close(); }
      } catch {
        // Sanitize before the Notte owner logs an exception during cleanup.
        throw new Error(`Vibium ${signal.aborted ? 'cancelled' : 'failed'} (session ${sessionId})`);
      }
    });
  } catch {
    failed = true;
    throw new Error(`Vibium ${signal.aborted ? 'cancelled' : 'failed'} (session ${sessionId})`);
  } finally {
    try { await driver.close(); }
    catch { if (!failed) throw new Error(`Vibium cleanup failed (session ${sessionId})`); }
  }
}
