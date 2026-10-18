import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { test } from 'node:test';
import { NotteClient, sessionStatus } from 'notte-sdk';
import { main } from '../src/main.ts';

test('Box with a hosted Notte browser', { skip: process.env.NOTTE_BOX_LIVE !== '1', timeout: 240_000 }, async t => {
  assert.ok(process.env.NOTTE_API_URL, 'Choose the test API explicitly');
  assert.ok(process.env.BOX_ACCESS_TOKEN, 'Set BOX_ACCESS_TOKEN');
  const original = globalThis.fetch;
  const headers = { Authorization: `Bearer ${process.env.BOX_ACCESS_TOKEN}` };
  const parent = process.env.BOX_FOLDER_ID;
  const created = await original('https://api.box.com/2.0/folders', {
    method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: `notte-test-${randomUUID()}`, parent: { id: parent ?? '0' } }),
    signal: AbortSignal.timeout(30_000),
  });
  assert.equal(created.status, 201, 'Could not create the isolated Box test folder');
  const folderId = (await created.json()).id as string;
  const files: string[] = [];

  async function owned(folder: string, run: (uploads: number[]) => Promise<void>) {
    const ids: string[] = [], uploads: number[] = [];
    process.env.BOX_FOLDER_ID = folder;
    globalThis.fetch = async (input, options) => {
      const response = await original(input, options);
      const url = new URL(input instanceof Request ? input.url : String(input));
      if (url.pathname === '/sessions/start' && response.ok) ids.push((await response.clone().json()).session_id);
      if (url.hostname === 'upload.box.com' && url.pathname === '/api/2.0/files/content') {
        uploads.push(response.status);
        if (response.ok) files.push(...(await response.clone().json()).entries.map((entry: { id: string }) => entry.id));
      }
      return response;
    };
    try { await run(uploads); }
    finally {
      globalThis.fetch = original;
      assert.equal(ids.length, 1, 'Expected one owned browser');
      const client = new NotteClient();
      let closed = false;
      for (let attempt = 0; attempt < 30; attempt++) {
        const result = await sessionStatus({ client: client.getClient(), path: { session_id: ids[0] }, throwOnError: true, signal: AbortSignal.timeout(15_000) });
        if (result.data.status === 'closed') { closed = true; break; }
        await new Promise(resolve => setTimeout(resolve, 500));
      }
      assert.ok(closed, 'Owned browser did not close');
    }
  }

  try {
    await t.test('original demo uploads a verified capture', () => owned(folderId, async uploads => {
      const result = await main();
      assert.ok(files.includes(result.box_file_id));
      assert.deepEqual(uploads, [201]);
    }));
    await t.test('real Box failure closes the browser', () => owned('not-a-folder', async uploads => {
      await assert.rejects(main(), /Box upload failed \(HTTP (400|404)\)/);
      assert.equal(uploads.length, 1);
      assert.ok([400, 404].includes(uploads[0]));
    }));
  } finally {
    globalThis.fetch = original;
    if (parent === undefined) delete process.env.BOX_FOLDER_ID; else process.env.BOX_FOLDER_ID = parent;
    for (const id of files) {
      const removed = await original(`https://api.box.com/2.0/files/${encodeURIComponent(id)}`, { method: 'DELETE', headers, signal: AbortSignal.timeout(30_000) });
      assert.equal(removed.status, 204, 'Could not remove a test-owned Box file');
    }
    const removed = await original(`https://api.box.com/2.0/folders/${encodeURIComponent(folderId)}`, { method: 'DELETE', headers, signal: AbortSignal.timeout(30_000) });
    assert.equal(removed.status, 204, 'Could not remove the empty test-owned Box folder');
  }
});
