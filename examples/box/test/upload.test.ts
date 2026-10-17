import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { test } from 'node:test';
import { uploadCapture } from '../src/main.ts';

function client(image: Buffer, corrupt = false): typeof fetch {
  return async (input, options) => {
    if (options?.method === 'POST') {
      assert.equal(String(input), 'https://upload.box.com/api/2.0/files/content');
      const form = options.body as FormData;
      assert.deepEqual([...form.keys()], ['attributes', 'file'], 'Box requires attributes before file content');
      assert.deepEqual(JSON.parse(String(form.get('attributes'))), { name: 'notte-session1.png', parent: { id: 'folder1' } });
      const file = form.get('file') as File;
      assert.equal(file.type, 'image/png');
      assert.deepEqual(Buffer.from(await file.arrayBuffer()), image);
      return Response.json({ entries: [{ id: 'file1' }] }, { status: 201 });
    }
    assert.equal(String(input), 'https://api.box.com/2.0/files/file1?fields=id,size,sha1');
    assert.equal(new Headers(options?.headers).get('Authorization'), 'Bearer test-only-token');
    return Response.json({ id: 'file1', size: image.length, sha1: corrupt ? 'wrong' : createHash('sha1').update(image).digest('hex') });
  };
}

test('uploads original bytes and verifies Box metadata', async () => {
  const image = Buffer.from('offline-browser-capture');
  assert.deepEqual(await uploadCapture(image, 'session1', 'test-only-token', 'folder1', client(image)), { box_file_id: 'file1', session_id: 'session1' });
});

test('rejects mismatched Box content', async () => {
  const image = Buffer.from('offline-browser-capture');
  await assert.rejects(uploadCapture(image, 'session1', 'test-only-token', 'folder1', client(image, true)), /Box content verification failed/);
});

test('provider errors do not expose authenticated request headers', async () => {
  const failing: typeof fetch = async () => { throw new Error('request headers contain test-only-token'); };
  await assert.rejects(uploadCapture(Buffer.from('test'), 'session1', 'test-only-token', 'folder1', failing), { message: 'Box upload failed' });
});

test('HTTP status remains actionable without provider secrets', async () => {
  const unauthorized: typeof fetch = async () => new Response('secret', { status: 401 });
  await assert.rejects(uploadCapture(Buffer.from('test'), 'session1', 'test-only-token', 'folder1', unauthorized), { message: 'Box upload failed (HTTP 401)' });
});

test('timeouts identify the failed step', async () => {
  const timeout: typeof fetch = async () => { throw new DOMException('secret', 'TimeoutError'); };
  await assert.rejects(uploadCapture(Buffer.from('test'), 'session1', 'test-only-token', 'folder1', timeout), { message: 'Box upload timed out' });
});
