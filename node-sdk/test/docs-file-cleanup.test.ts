import { afterEach, expect, it, vi } from 'vitest';

const fixture = vi.hoisted(() => ({
  uploads: 0,
  deleted: [] as string[],
  stopped: false,
  failure: '',
}));

vi.mock('notte-sdk', () => {
  class RemoteFileStorage {
    sessionId = 'owned-session';
    async upload() {
      fixture.uploads++;
      if (fixture.failure === 'second-upload' && fixture.uploads === 2) throw new Error('upload failed');
      return { id: String(fixture.uploads) };
    }
    async list() {
      if (fixture.failure === 'list') throw new Error('list failed');
      return { files: [] };
    }
    async delete(id: string) {
      fixture.deleted.push(id);
      if (fixture.failure === 'delete' && id === '1') throw new Error('delete failed');
    }
  }
  class NotteClient {
    FileStorage() { return new RemoteFileStorage(); }
    getClient() { return {}; }
    Session() {
      return {
        async use(callback: (session: object) => Promise<void>) {
          try { await callback({}); } finally { fixture.stopped = true; }
        },
      };
    }
  }
  return {
    NotteClient,
    RemoteFileStorage,
    sessionStatus: async () => {
      if (fixture.failure !== 'list') throw new Error('status failed');
      return { data: { session_id: 'owned-session', status: 'closed' } };
    },
  };
});

afterEach(() => vi.restoreAllMocks());

for (const example of ['uploading_files', 'attach_before_starting']) {
  for (const failure of ['status', 'list', 'delete', ...(example === 'uploading_files' ? ['second-upload'] : [])]) {
    it(`${example} cleans successful uploads after ${failure} failure`, async () => {
      vi.resetModules();
      Object.assign(fixture, { uploads: 0, deleted: [], stopped: false, failure });
      vi.spyOn(console, 'log').mockImplementation(() => {});
      const { RemoteFileStorage } = await import('notte-sdk');
      const original = RemoteFileStorage.prototype.upload;
      await expect(import(`../../docs/src/testers/file-storage/${example}.ts`)).rejects.toThrow();
      const count = example === 'attach_before_starting' || failure === 'second-upload' ? 1 : 2;
      expect(fixture.deleted).toEqual(Array.from({ length: count }, (_, i) => String(i + 1)));
      expect(fixture.stopped).toBe(true);
      expect(RemoteFileStorage.prototype.upload).toBe(original);
    });
  }
}
