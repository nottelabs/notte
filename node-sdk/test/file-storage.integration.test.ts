import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { config } from 'dotenv';
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { NotteClient } from '@/client';
import type { Session, SessionOptions } from '@/session';
import { InvalidRequestError, NotteAPIError } from '@/errors';
import { FileExistsError, FileNotFoundError, RemoteFileStorage, type SessionFile } from '@/files';

config();

// Self-hosted fixtures shared with tests/integration/sdk/file_storage in the Python suite.
const FIXTURE_HOST = 'https://test-resources-lovat.vercel.app';
const UPLOAD_FIXTURE_URL = `${FIXTURE_HOST}/upload_fixture.html`;
const TEXT_FIXTURE_NAME = 'text1.txt';

function isFileApiMissing(error: unknown): boolean {
  return error instanceof NotteAPIError && error.statusCode === 404;
}

async function waitForDownload(
  storage: RemoteFileStorage,
  filenameSuffix: string,
  timeoutMs = 20_000,
): Promise<SessionFile[]> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const { files } = await storage.list({ source: 'session_download', limit: 1000 });
    const matching = files.filter(file => file.filename.endsWith(filenameSuffix));
    if (matching.length > 0) {
      return matching;
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  return [];
}

describe('File storage integration', () => {
  let client: NotteClient;

  beforeAll(() => {
    if (!process.env.NOTTE_API_KEY) {
      throw new Error('NOTTE_API_KEY environment variable is required for integration tests');
    }
    client = new NotteClient();
  });

  // Mirrors test_upload_non_existent_file_should_raise_error.
  it('rejects uploading a non-existent local file before calling the API', async () => {
    const storage = new RemoteFileStorage(client, 'session-id');
    await expect(storage.upload(join(tmpdir(), 'notte-non-existent-file.txt'))).rejects.toBeInstanceOf(InvalidRequestError);
  });

  it('requires a session ID before any operation', async () => {
    const storage = new RemoteFileStorage(client);
    await expect(storage.list()).rejects.toBeInstanceOf(InvalidRequestError);
  });

  describe('with a session using file storage', () => {
    let session: Session;
    let storage: RemoteFileStorage;
    let tmpPath = '';
    let fileApiAvailable = true;

    beforeAll(async () => {
      // `use_file_storage` is set by `Session` when a storage is attached; until
      // that lands, request it explicitly on the start payload.
      session = client.Session({ proxies: false, use_file_storage: true } as SessionOptions);
      await session.start();
      const sessionId = session.getId();
      if (!sessionId) {
        throw new Error('session did not start');
      }
      storage = client.FileStorage(sessionId);
      try {
        await storage.list();
      } catch (error) {
        if (!isFileApiMissing(error)) throw error;
        fileApiAvailable = false;
      }
    });

    afterAll(async () => {
      await session?.stop();
    });

    beforeEach(async ctx => {
      if (!fileApiAvailable) {
        ctx.skip();
      }
      tmpPath = await mkdtemp(join(tmpdir(), 'notte-storage-'));
    });

    afterEach(async () => {
      // A dynamic skip in beforeEach leaves tmpPath unset; Vitest still runs afterEach.
      if (tmpPath) {
        await rm(tmpPath, { recursive: true, force: true });
        tmpPath = '';
      }
    });

    it('uploads, lists, reads metadata, downloads and deletes a file', async () => {
      const local = join(tmpPath, 'input.txt');
      await writeFile(local, 'original file!\nnode sdk');

      const uploaded = await storage.upload(local);
      expect(uploaded.filename).toBe('input.txt');
      expect(uploaded.session_id).toBe(storage.sessionId);
      expect(uploaded.size).toBe(23);
      expect(uploaded.source).toBe('user_upload');

      try {
        const page = await storage.list({ source: 'user_upload', limit: 1000 });
        expect(page.files.some(file => file.id === uploaded.id)).toBe(true);
        expect(page.total).toBeGreaterThanOrEqual(1);

        const metadata = await storage.metadata(uploaded.id);
        expect(metadata).toEqual(uploaded);

        // client.Files(sessionId) sees the same session files.
        const files = client.Files(storage.sessionId);
        await expect(files.metadata(uploaded.id)).resolves.toEqual(uploaded);

        // Download to a directory: written atomically under the server filename.
        const downloadDir = join(tmpPath, 'downloads');
        const destination = await storage.download(uploaded.id, downloadDir);
        expect(destination).toBe(join(downloadDir, 'input.txt'));
        await expect(readFile(destination, 'utf8')).resolves.toBe('original file!\nnode sdk');
        await expect(readdir(downloadDir)).resolves.toEqual(['input.txt']);

        // A second download refuses to overwrite unless forced.
        await expect(storage.download(uploaded.id, downloadDir)).rejects.toBeInstanceOf(FileExistsError);
        await writeFile(destination, 'stale');
        await expect(storage.download(uploaded.id, downloadDir, { force: true })).resolves.toBe(destination);
        await expect(readFile(destination, 'utf8')).resolves.toBe('original file!\nnode sdk');

        // In-memory download.
        const blob = await storage.downloadBlob(uploaded.id);
        await expect(blob.text()).resolves.toBe('original file!\nnode sdk');

        const stream = await storage.stream(uploaded.id);
        await expect(new Response(stream).text()).resolves.toBe('original file!\nnode sdk');
      } finally {
        await storage.delete(uploaded.id);
      }

      const afterDelete = await storage.list({ source: 'user_upload', limit: 1000 });
      expect(afterDelete.files.some(file => file.id === uploaded.id)).toBe(false);
      await expect(storage.metadata(uploaded.id)).rejects.toBeInstanceOf(FileNotFoundError);
      await expect(storage.download(uploaded.id, tmpPath)).rejects.toBeInstanceOf(FileNotFoundError);
    });

    it('uploads in-memory bytes under an explicit filename', async () => {
      const uploaded = await storage.upload(Buffer.from('{"hello":"world"}'), 'payload.json');
      try {
        expect(uploaded.filename).toBe('payload.json');
        expect(uploaded.size).toBe(17);
        const blob = await storage.downloadBlob(uploaded.id);
        await expect(blob.text()).resolves.toBe('{"hello":"world"}');
      } finally {
        await storage.delete(uploaded.id);
      }
    });

    it('rejects an unknown file ID with FileNotFoundError', async () => {
      await expect(storage.metadata('00000000-0000-0000-0000-000000000000')).rejects.toBeInstanceOf(FileNotFoundError);
    });

    // Mirrors test_upload_against_local_fixture: the uploaded file is visible to the page.
    it('makes an uploaded file available to the browser', async () => {
      const content = 'original file!\nnode sdk upload fixture\n';
      const local = join(tmpPath, TEXT_FIXTURE_NAME);
      await writeFile(local, content);
      const uploaded = await storage.upload(local);
      try {
        expect(uploaded.filename).toBe(TEXT_FIXTURE_NAME);

        await session.execute({ type: 'goto', url: UPLOAD_FIXTURE_URL });
        await session.execute({ type: 'upload_file', selector: '#file-input', file_path: TEXT_FIXTURE_NAME });
        await session.execute({ type: 'click', selector: '#validate-btn' });

        const page = await session.scrape();
        const expectedHexPrefix = Buffer.from(content).subarray(0, 16).toString('hex');

        expect(page).not.toContain('NO_FILE_SELECTED');
        expect(page).toContain(TEXT_FIXTURE_NAME);
        expect(page).toContain('text/plain');
        expect(page).toContain(expectedHexPrefix);
      } finally {
        await storage.delete(uploaded.id);
      }
    });

    // Mirrors test_download_against_local_fixture (raw_txt) and the read-only
    // guarantee of test_download_file_action_is_strictly_readonly: browser
    // downloads stay remote until `download()` is called explicitly.
    it('collects browser downloads remotely and downloads them locally on demand', async () => {
      const expectedBytes = Buffer.from(await (await fetch(`${FIXTURE_HOST}/${TEXT_FIXTURE_NAME}`)).arrayBuffer());

      await session.execute({ type: 'goto', url: `${FIXTURE_HOST}/${TEXT_FIXTURE_NAME}` });
      await session.execute({ type: 'download_file', selector: 'body' });

      const matching = await waitForDownload(storage, TEXT_FIXTURE_NAME);
      expect(matching, `expected exactly one file ending with ${TEXT_FIXTURE_NAME}`).toHaveLength(1);
      const stored = matching[0]!;
      expect(stored.source).toBe('session_download');

      // Nothing has been written locally yet.
      await expect(readdir(tmpPath)).resolves.toEqual([]);

      try {
        const localPath = await storage.download(stored.id, tmpPath);
        expect(localPath).toBe(join(tmpPath, stored.filename));
        await expect(readFile(localPath)).resolves.toEqual(expectedBytes);
      } finally {
        await storage.delete(stored.id);
      }
    });
  });
});
