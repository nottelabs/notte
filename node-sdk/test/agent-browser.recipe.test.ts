import { promisify } from 'node:util';
import { afterEach, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.doUnmock('notte-sdk');
  vi.doUnmock('node:child_process');
  vi.resetModules();
});

it.each(['success', 'invalid_title', 'close_failure', 'both', 'invalid_json'])('recipe privacy and cleanup: %s', async mode => {
  const cdp = 'wss://fixture.invalid/browser?capability=private-fixture';
  const calls: string[] = [];
  let closed = false;
  const execute = Object.assign(() => {}, { [promisify.custom]: async (_binary: string, args: string[], options: { env: Record<string, string> }) => {
    expect(args).not.toContain(cdp);
    expect(options.env.AGENT_BROWSER_CDP).toBe(cdp);
    const command = args[3];
    calls.push(command);
    if (command === 'open' && mode === 'invalid_json') return { stdout: cdp };
    if (command === 'close' && ['close_failure', 'both'].includes(mode)) throw new Error(cdp);
    return { stdout: JSON.stringify({ success: true, data: { title: ['invalid_title', 'both'].includes(mode) ? 42 : 'Example Domain' } }) };
  } });
  vi.doMock('node:child_process', () => ({ execFile: execute }));
  vi.doMock('notte-sdk', () => ({ NotteClient: class {
    Session() {
      return { use: async (callback: (session: { getId: () => string; cdpUrl: () => Promise<string> }) => Promise<unknown>) => {
        try { return await callback({ getId: () => 'owned-fixture', cdpUrl: async () => cdp }); }
        finally { closed = true; }
      } };
    }
  } }));
  vi.resetModules();
  const recipe = new URL('../../docs/src/testers/integrations/agent_browser.ts', import.meta.url);
  const operation = import(recipe.href);
  if (mode === 'success') expect((await operation).result).toEqual({ title: 'Example Domain', session_id: 'owned-fixture' });
  else await expect(operation).rejects.toThrow(['invalid_title', 'both'].includes(mode) ? 'The title was not returned' : 'agent-browser command failed');
  expect(calls.at(-1)).toBe('close');
  expect(closed).toBe(true);
});
