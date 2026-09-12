import { afterEach, expect, it, vi } from 'vitest';

const fixture = vi.hoisted(() => ({ mode: '', stopped: false }));
vi.mock('notte-sdk', () => {
  class Session {
    async execute(action: { type: string }) {
      if (action.type === 'upload_file' && fixture.mode === 'action') throw new Error('upload failed');
      return {};
    }
    async page() {
      return { locator: () => ({ evaluate: async () => ({
        name: 'text1.txt', text: fixture.mode === 'contents' ? 'wrong' : 'fixture contents',
      }) }) };
    }
    async status() { return { session_id: 'owned', status: 'active' }; }
    async use(callback: (session: Session) => Promise<void>) {
      try { await callback(this); }
      finally { fixture.stopped = true; }
    }
  }
  return { Session, NotteClient: class { Session() { return new Session(); } } };
});

afterEach(() => vi.unstubAllGlobals());

it.each(['success', 'action', 'contents'])('URL upload validates contents and cleans up after %s', async mode => {
  vi.resetModules();
  Object.assign(fixture, { mode, stopped: false });
  vi.stubGlobal('fetch', vi.fn(async () => new Response('fixture contents')));
  const { Session } = await vi.importMock<{ Session: { prototype: { execute: unknown } } }>('notte-sdk');
  const original = Session.prototype.execute;
  const example = 'url_upload';
  const execution = import(`../../docs/src/testers/file-storage/${example}.ts`);
  if (mode === 'success') {
    await expect(execution).resolves.toMatchObject({ status: { session_id: 'owned', status: 'active' } });
  } else if (mode === 'action') {
    await expect(execution).rejects.toThrow('upload failed');
  } else {
    await expect(execution).rejects.toThrow();
  }
  expect(fixture.stopped).toBe(true);
  expect(Session.prototype.execute).toBe(original);
});
