import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SessionFiles } from '@/files';
import type { Client } from '@/lib/client/client/types.gen';
import { createClient } from '@/lib/client/client';

it('sends multipart bytes through the actual generated client', async () => {
  const fetch = vi.fn<typeof globalThis.fetch>(async input => {
    const request = input instanceof Request ? input : new Request(input);
    expect(request.headers.get('content-type')).toMatch(/^multipart\/form-data; boundary=/);
    const body = await request.formData();
    const file = body.get('file') as File;
    expect(file.name).toBe('test.txt');
    expect(await file.text()).toBe('file bytes');
    return Response.json({ id: 'file' });
  });
  const client = createClient({ baseUrl: 'https://example.com', fetch });
  await expect(new SessionFiles(client, 'session').upload(new Blob(['file bytes']), 'test.txt')).resolves.toEqual({ id: 'file' });
});

describe('SessionFiles', () => {
  const request = vi.fn();
  const client = { request } as unknown as Client;

  beforeEach(() => {
    request.mockReset();
  });

  it('uploads a multipart file with the requested filename', async () => {
    const metadata = { id: 'file-id', filename: 'report.pdf' };
    request.mockResolvedValue({ data: metadata });
    const files = new SessionFiles(client, 'session/id');
    const blob = new Blob(['pdf bytes'], { type: 'application/pdf' });

    await expect(files.upload(blob, 'report.pdf')).resolves.toBe(metadata);

    expect(request).toHaveBeenCalledOnce();
    const options = request.mock.calls[0]![0];
    expect(options.method).toBe('POST');
    expect(options.url).toBe('/sessions/session%2Fid/files');
    expect(options.body).toBeInstanceOf(FormData);
    const uploaded = (options.body as FormData).get('file') as File;
    expect(uploaded.name).toBe('report.pdf');
    expect(await uploaded.text()).toBe('pdf bytes');
  });

  it('forwards source and pagination when listing files', async () => {
    const page = { files: [], total: 0, limit: 25, offset: 50 };
    request.mockResolvedValue({ data: page });

    await expect(
      new SessionFiles(client, 'session-id').list({ source: 'session_download', limit: 25, offset: 50 }),
    ).resolves.toBe(page);

    expect(request).toHaveBeenCalledWith({
      method: 'GET',
      url: '/sessions/session-id/files',
      query: { source: 'session_download', limit: 25, offset: 50 },
    });
  });

  it('downloads binary data and safely encodes the file ID', async () => {
    const blob = new Blob(['download body']);
    request.mockResolvedValue({ data: blob });

    await expect(new SessionFiles(client, 'session-id').download('file/id')).resolves.toBe(blob);

    expect(request).toHaveBeenCalledWith({
      method: 'GET',
      url: '/sessions/session-id/files/file%2Fid',
      parseAs: 'blob',
    });
  });

  it('deletes a session file', async () => {
    request.mockResolvedValue({ data: undefined });

    await expect(new SessionFiles(client, 'session-id').delete('file-id')).resolves.toBeUndefined();
    expect(request).toHaveBeenCalledWith({ method: 'DELETE', url: '/sessions/session-id/files/file-id' });
  });

  it.each([
    ['upload', () => new SessionFiles(client, 'session-id').upload(new Blob(['x']), 'x.txt')],
    ['list', () => new SessionFiles(client, 'session-id').list()],
    ['download', () => new SessionFiles(client, 'session-id').download('file-id')],
    ['delete', () => new SessionFiles(client, 'session-id').delete('file-id')],
  ])('surfaces %s API failures', async (_operation, invoke) => {
    request.mockResolvedValue({ error: { detail: 'failed' } });
    await expect(invoke()).rejects.toThrow(/Failed to|Failed/);
  });
});
