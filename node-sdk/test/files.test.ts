import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const mocks = vi.hoisted(() => ({
  uploadSessionFile: vi.fn(),
  listSessionFiles: vi.fn(),
  downloadSessionFile: vi.fn(),
  deleteSessionFile: vi.fn(),
}));

vi.mock('@/lib/client/sdk.gen', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/client/sdk.gen')>();
  return { ...actual, ...mocks };
});

import type { NotteClient } from '@/client';
import { InvalidRequestError, NotteAPIError } from '@/errors';
import { FileExistsError, FileNotFoundError, RemoteFileStorage, SessionFiles, sanitizeFilename } from '@/files';
import type { SessionFile } from '@/files';
import type { Client } from '@/lib/client/client/types.gen';
import { createClient } from '@/lib/client/client';

const generatedClient = { id: 'generated-client' } as unknown as Client;
const client = { getClient: () => generatedClient } as unknown as NotteClient;

function fileMetadata(overrides: Partial<SessionFile> = {}): SessionFile {
  return {
    id: 'file-id',
    session_id: 'session-id',
    filename: 'input.txt',
    mime_type: 'text/plain',
    size: 5,
    checksum: 'a'.repeat(64),
    created_at: '2026-08-21T00:00:00Z',
    expires_at: '2026-08-22T00:00:00Z',
    source: 'user_upload',
    ...overrides,
  };
}

function page(files: SessionFile[], total = files.length, offset = 0) {
  return { data: { files, total, limit: 1000, offset } };
}

function apiError(status = 500): NotteAPIError {
  return new NotteAPIError('/sessions/session-id/files', status, { message: 'failed' });
}

let tmpPath: string;

beforeEach(async () => {
  Object.values(mocks).forEach(mock => mock.mockReset());
  tmpPath = await mkdtemp(join(tmpdir(), 'notte-files-'));
});

afterEach(async () => {
  await rm(tmpPath, { recursive: true, force: true });
});

describe('multipart upload through the real generated client', () => {
  it('sends multipart bytes with the requested filename', async () => {
    const { uploadSessionFile } = await vi.importActual<typeof import('@/lib/client/sdk.gen')>('@/lib/client/sdk.gen');
    mocks.uploadSessionFile.mockImplementation(uploadSessionFile);
    const fetch = vi.fn<typeof globalThis.fetch>(async input => {
      const request = input instanceof Request ? input : new Request(input);
      expect(request.headers.get('content-type')).toMatch(/^multipart\/form-data; boundary=/);
      const body = await request.formData();
      const file = body.get('file') as File;
      expect(file.name).toBe('test.txt');
      expect(file.type).toBe('text/plain');
      expect(await file.text()).toBe('file bytes');
      return Response.json({ id: 'file' }, { status: 201 });
    });
    const realClient = createClient({ baseUrl: 'https://example.com', fetch });
    await expect(new SessionFiles(realClient, 'session').upload(new Blob(['file bytes']), 'test.txt')).resolves.toEqual({
      id: 'file',
    });
    expect(fetch).toHaveBeenCalledOnce();
  });
});

describe('SessionFiles', () => {
  it('uploads a Blob wrapped as a named File', async () => {
    const metadata = fileMetadata({ filename: 'report.pdf' });
    mocks.uploadSessionFile.mockResolvedValue({ data: metadata });
    const files = new SessionFiles(generatedClient, 'session-id');

    await expect(files.upload(new Blob(['pdf bytes'], { type: 'application/pdf' }), 'report.pdf')).resolves.toBe(metadata);

    const options = mocks.uploadSessionFile.mock.calls[0]![0];
    expect(options.client).toBe(generatedClient);
    expect(options.path).toEqual({ session_id: 'session-id' });
    const uploaded = options.body.file as File;
    expect(uploaded).toBeInstanceOf(File);
    expect(uploaded.name).toBe('report.pdf');
    expect(uploaded.type).toBe('application/pdf');
    expect(await uploaded.text()).toBe('pdf bytes');
  });

  it('uploads raw bytes and guesses the MIME type from the filename', async () => {
    mocks.uploadSessionFile.mockResolvedValue({ data: fileMetadata() });
    await new SessionFiles(generatedClient, 'session-id').upload(Buffer.from('hello'), 'hello.txt');
    const uploaded = mocks.uploadSessionFile.mock.calls[0]![0].body.file as File;
    expect(uploaded.name).toBe('hello.txt');
    expect(uploaded.type).toBe('text/plain');
    expect(await uploaded.text()).toBe('hello');
  });

  it('forwards source and pagination when listing files', async () => {
    const result = { files: [], total: 0, limit: 25, offset: 50 };
    mocks.listSessionFiles.mockResolvedValue({ data: result });

    await expect(
      new SessionFiles(generatedClient, 'session-id').list({ source: 'session_download', limit: 25, offset: 50 }),
    ).resolves.toBe(result);

    expect(mocks.listSessionFiles).toHaveBeenCalledWith(
      expect.objectContaining({
        path: { session_id: 'session-id' },
        query: { source: 'session_download', limit: 25, offset: 50 },
      }),
    );
  });

  it('defaults to limit 100 and offset 0', async () => {
    mocks.listSessionFiles.mockResolvedValue(page([]));
    await new SessionFiles(generatedClient, 'session-id').list();
    expect(mocks.listSessionFiles.mock.calls[0]![0].query).toEqual({ limit: 100, offset: 0, source: undefined });
  });

  it('downloads binary data as a Blob', async () => {
    const blob = new Blob(['download body']);
    mocks.downloadSessionFile.mockResolvedValue({ data: blob });

    await expect(new SessionFiles(generatedClient, 'session-id').download('file-id')).resolves.toBe(blob);

    expect(mocks.downloadSessionFile).toHaveBeenCalledWith(
      expect.objectContaining({ path: { session_id: 'session-id', file_id: 'file-id' }, parseAs: 'blob' }),
    );
  });

  it('deletes a session file', async () => {
    mocks.deleteSessionFile.mockResolvedValue({ data: undefined });
    await expect(new SessionFiles(generatedClient, 'session-id').delete('file-id')).resolves.toBeUndefined();
    expect(mocks.deleteSessionFile).toHaveBeenCalledWith(
      expect.objectContaining({ path: { session_id: 'session-id', file_id: 'file-id' } }),
    );
  });

  it('finds metadata across pages and rejects unknown IDs', async () => {
    const first = fileMetadata({ id: 'first' });
    const second = fileMetadata({ id: 'second' });
    mocks.listSessionFiles.mockResolvedValueOnce(page([first], 2, 0)).mockResolvedValueOnce(page([second], 2, 1));
    const files = new SessionFiles(generatedClient, 'session-id');
    await expect(files.metadata('second')).resolves.toBe(second);
    expect(mocks.listSessionFiles.mock.calls.map(([options]) => options.query.offset)).toEqual([0, 1]);

    mocks.listSessionFiles.mockReset();
    mocks.listSessionFiles.mockResolvedValue(page([first]));
    const failure = files.metadata('missing');
    await expect(failure).rejects.toBeInstanceOf(FileNotFoundError);
    await expect(failure).rejects.toThrow('File missing was not found in session session-id');
  });

  it('rejects with FileNotFoundError on an empty session', async () => {
    mocks.listSessionFiles.mockResolvedValue(page([]));
    await expect(new SessionFiles(generatedClient, 'session-id').metadata('x')).rejects.toBeInstanceOf(FileNotFoundError);
    expect(mocks.listSessionFiles).toHaveBeenCalledOnce();
  });

  it.each([
    ['upload', () => new SessionFiles(generatedClient, 'session-id').upload(new Blob(['x']), 'x.txt'), mocks.uploadSessionFile],
    ['list', () => new SessionFiles(generatedClient, 'session-id').list(), mocks.listSessionFiles],
    ['download', () => new SessionFiles(generatedClient, 'session-id').download('file-id'), mocks.downloadSessionFile],
    ['delete', () => new SessionFiles(generatedClient, 'session-id').delete('file-id'), mocks.deleteSessionFile],
  ])('propagates %s API failures as NotteAPIError', async (_operation, invoke, mock) => {
    mock.mockRejectedValue(apiError(503));
    const failure = invoke();
    await expect(failure).rejects.toBeInstanceOf(NotteAPIError);
    await expect(failure).rejects.toMatchObject({ statusCode: 503 });
  });
});

describe('sanitizeFilename', () => {
  it.each([
    ['input.txt', 'input.txt'],
    ['../../secret.txt', 'secret.txt'],
    ['..\\..\\secret.txt', 'secret.txt'],
    ['/tmp/secret.txt', 'secret.txt'],
    ['C:\\Users\\me\\secret.txt', 'secret.txt'],
    ['C:secret.txt', 'secret.txt'],
    ['dir/sub/', 'sub'],
    ['..', '..'],
    ['', ''],
  ])('reduces %j to %j', (input, expected) => {
    expect(sanitizeFilename(input)).toBe(expected);
  });
});

describe('RemoteFileStorage', () => {
  it('requires a session for every operation', async () => {
    const storage = new RemoteFileStorage(client);
    expect(storage.isBound).toBe(false);
    expect(() => storage.sessionId).toThrow(InvalidRequestError);
    await expect(storage.list()).rejects.toThrow(/session ID/);
    await expect(storage.upload(Buffer.from('x'), 'x.txt')).rejects.toBeInstanceOf(InvalidRequestError);
    expect(mocks.listSessionFiles).not.toHaveBeenCalled();
    expect(mocks.uploadSessionFile).not.toHaveBeenCalled();
  });

  it('binds with setSessionId', async () => {
    mocks.listSessionFiles.mockResolvedValue(page([]));
    const storage = new RemoteFileStorage(client);
    storage.setSessionId('session-id');
    expect(storage.sessionId).toBe('session-id');
    await storage.list();
    expect(mocks.listSessionFiles.mock.calls[0]![0].path).toEqual({ session_id: 'session-id' });
  });

  it('is cloned when reused across sessions', () => {
    const storage = new RemoteFileStorage(client);

    const first = storage.forSession('session-a');
    const again = storage.forSession('session-a');
    const second = storage.forSession('session-b');

    expect(first).toBe(storage);
    expect(again).toBe(storage);
    expect(first.sessionId).toBe('session-a');
    expect(second).not.toBe(storage);
    expect(second.sessionId).toBe('session-b');
    expect(second.client).toBe(storage.client);
  });

  it('uploads a local path, deriving the filename', async () => {
    const local = join(tmpPath, 'input.txt');
    await writeFile(local, 'hello');
    const metadata = fileMetadata();
    mocks.uploadSessionFile.mockResolvedValue({ data: metadata });

    await expect(new RemoteFileStorage(client, 'session-id').upload(local)).resolves.toBe(metadata);

    const options = mocks.uploadSessionFile.mock.calls[0]![0];
    expect(options.client).toBe(generatedClient);
    expect(options.path).toEqual({ session_id: 'session-id' });
    const uploaded = options.body.file as File;
    expect(uploaded.name).toBe('input.txt');
    expect(uploaded.type).toBe('text/plain');
    expect(await uploaded.text()).toBe('hello');
  });

  it('honours an explicit upload filename', async () => {
    const local = join(tmpPath, 'input.txt');
    await writeFile(local, 'hello');
    mocks.uploadSessionFile.mockResolvedValue({ data: fileMetadata() });

    await new RemoteFileStorage(client, 'session-id').upload(local, 'renamed.txt');
    expect((mocks.uploadSessionFile.mock.calls[0]![0].body.file as File).name).toBe('renamed.txt');
  });

  it('rejects a non-existent path or a directory before calling the API', async () => {
    const storage = new RemoteFileStorage(client, 'session-id');
    const missing = join(tmpPath, 'non_existent_file.txt');
    const failure = storage.upload(missing);
    await expect(failure).rejects.toBeInstanceOf(InvalidRequestError);
    await expect(failure).rejects.toThrow(`Cannot upload file ${missing}: it is not a file`);
    await expect(storage.upload(tmpPath)).rejects.toBeInstanceOf(InvalidRequestError);
    expect(mocks.uploadSessionFile).not.toHaveBeenCalled();
  });

  it('uploads Blobs, Files and buffers', async () => {
    mocks.uploadSessionFile.mockResolvedValue({ data: fileMetadata() });
    const storage = new RemoteFileStorage(client, 'session-id');

    await storage.upload(new Blob(['a']));
    await storage.upload(new File(['b'], 'named.txt'));
    await storage.upload(Buffer.from('c'), 'buffer.bin');

    const names = mocks.uploadSessionFile.mock.calls.map(([options]) => (options.body.file as File).name);
    expect(names).toEqual(['file', 'named.txt', 'buffer.bin']);
  });

  it('lists, reads metadata, downloads a Blob and deletes through the session client', async () => {
    const metadata = fileMetadata();
    mocks.listSessionFiles.mockResolvedValue(page([metadata]));
    mocks.downloadSessionFile.mockResolvedValue({ data: new Blob(['hello']) });
    mocks.deleteSessionFile.mockResolvedValue({ data: undefined });
    const storage = new RemoteFileStorage(client, 'session-id');

    await expect(storage.list({ source: 'user_upload' })).resolves.toEqual(page([metadata]).data);
    await expect(storage.metadata('file-id')).resolves.toBe(metadata);
    await expect((await storage.downloadBlob('file-id')).text()).resolves.toBe('hello');
    await storage.delete('file-id');

    expect(mocks.listSessionFiles.mock.calls[0]![0].query).toEqual({ source: 'user_upload', limit: 100, offset: 0 });
    expect(mocks.deleteSessionFile.mock.calls[0]![0].path).toEqual({ session_id: 'session-id', file_id: 'file-id' });
  });

  it('streams file bytes through the bound session', async () => {
    const body = new Blob(['streamed content']).stream();
    mocks.downloadSessionFile.mockResolvedValue({ data: body });
    const storage = new RemoteFileStorage(client, 'session-id');

    const stream = await storage.stream('file-id');
    expect(stream).toBe(body);
    await expect(new Response(stream).text()).resolves.toBe('streamed content');
    expect(mocks.downloadSessionFile).toHaveBeenCalledWith(expect.objectContaining({
      path: { session_id: 'session-id', file_id: 'file-id' },
      parseAs: 'stream',
    }));
  });

  describe('download to disk', () => {
    function mockDownload(metadata: SessionFile, content: string) {
      mocks.listSessionFiles.mockResolvedValue(page([metadata]));
      mocks.downloadSessionFile.mockImplementation(async () => ({ data: new Blob([content]).stream() }));
    }

    it('writes the file under the local directory and returns its path', async () => {
      mockDownload(fileMetadata(), 'hello');
      const storage = new RemoteFileStorage(client, 'session-id');

      const destination = await storage.download('file-id', tmpPath);

      expect(destination).toBe(join(tmpPath, 'input.txt'));
      await expect(readFile(destination, 'utf8')).resolves.toBe('hello');
      expect(mocks.downloadSessionFile).toHaveBeenCalledWith(
        expect.objectContaining({ path: { session_id: 'session-id', file_id: 'file-id' }, parseAs: 'stream' }),
      );
    });

    it('creates missing directories', async () => {
      mockDownload(fileMetadata(), 'hello');
      const nested = join(tmpPath, 'nested', 'dir');
      const destination = await new RemoteFileStorage(client, 'session-id').download('file-id', nested);
      expect(destination).toBe(join(nested, 'input.txt'));
      await expect(readFile(destination, 'utf8')).resolves.toBe('hello');
    });

    it.each(['../../secret.txt', '..\\..\\secret.txt', '/tmp/secret.txt'])('sanitizes the server filename %j', async filename => {
      mockDownload(fileMetadata({ filename }), 'hello');
      const destination = await new RemoteFileStorage(client, 'session-id').download('file-id', tmpPath);
      expect(destination).toBe(join(tmpPath, 'secret.txt'));
      await expect(readFile(destination, 'utf8')).resolves.toBe('hello');
    });

    it.each(['..', '.', '/', ''])('refuses the unsafe server filename %j', async filename => {
      mockDownload(fileMetadata({ filename }), 'hello');
      await expect(new RemoteFileStorage(client, 'session-id').download('file-id', tmpPath)).rejects.toThrow(
        /Unsafe filename returned for file file-id/,
      );
      expect(mocks.downloadSessionFile).not.toHaveBeenCalled();
    });

    it('rejects with FileExistsError unless force is set', async () => {
      mockDownload(fileMetadata(), 'new content');
      const destination = join(tmpPath, 'input.txt');
      await writeFile(destination, 'old content');
      const storage = new RemoteFileStorage(client, 'session-id');

      const failure = storage.download('file-id', tmpPath);
      await expect(failure).rejects.toBeInstanceOf(FileExistsError);
      await expect(failure).rejects.toThrow(`${destination} already exists; pass force: true to overwrite it`);
      await expect(readFile(destination, 'utf8')).resolves.toBe('old content');
      expect(mocks.downloadSessionFile).not.toHaveBeenCalled();

      await expect(storage.download('file-id', tmpPath, { force: true })).resolves.toBe(destination);
      await expect(readFile(destination, 'utf8')).resolves.toBe('new content');
    });

    it('does not follow a predictable temporary symlink', async () => {
      const outside = join(tmpPath, '..', `notte-outside-${process.pid}.txt`);
      await writeFile(outside, 'safe');
      try {
        await symlink(outside, join(tmpPath, '.input.txt.part'));
        mockDownload(fileMetadata(), 'download');

        const destination = await new RemoteFileStorage(client, 'session-id').download('file-id', tmpPath);

        await expect(readFile(destination, 'utf8')).resolves.toBe('download');
        await expect(readFile(outside, 'utf8')).resolves.toBe('safe');
      } finally {
        await rm(outside, { force: true });
      }
    });

    it('cleans up the temporary file when the stream fails', async () => {
      mocks.listSessionFiles.mockResolvedValue(page([fileMetadata()]));
      mocks.downloadSessionFile.mockResolvedValue({
        data: new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(new TextEncoder().encode('partial'));
            controller.error(new Error('connection reset'));
          },
        }),
      });

      await expect(new RemoteFileStorage(client, 'session-id').download('file-id', tmpPath)).rejects.toThrow('connection reset');

      const { readdir } = await import('node:fs/promises');
      await expect(readdir(tmpPath)).resolves.toEqual([]);
    });

    it('propagates download API errors', async () => {
      mocks.listSessionFiles.mockResolvedValue(page([fileMetadata()]));
      mocks.downloadSessionFile.mockRejectedValue(apiError(410));
      await expect(new RemoteFileStorage(client, 'session-id').download('file-id', tmpPath)).rejects.toMatchObject({
        statusCode: 410,
      });
    });
  });
});
