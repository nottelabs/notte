// @sniptest filename=attach_before_starting.ts
// @sniptest show=1-11
import { NotteClient } from 'notte-sdk';
import { readFile } from 'node:fs/promises';

const client = new NotteClient();

const status = await client.Session().use(async session => {
  // Storage is always available and scoped to the session.
  const storage = client.Files(session.getId()!);
  await storage.upload(new Blob([new Uint8Array(await readFile('file.pdf'))]), 'file.pdf');
  return await session.status();
});

import assert from 'node:assert/strict';
const storage = client.Files(status.session_id);
const { files } = await storage.list({ source: 'user_upload' });
try {
  assert.deepEqual(files.map(file => file.filename), ['file.pdf']);
  assert.deepEqual(Buffer.from(await (await storage.download(files[0].id)).arrayBuffer()), await readFile('file.pdf'));
} finally {
  for (const file of files) await storage.delete(file.id);
}
export { status };
