// @sniptest filename=uploading_files.ts
// @sniptest show=1-12
import { NotteClient } from 'notte-sdk';
import { readFile } from 'node:fs/promises';

const client = new NotteClient();
const status = await client.Session().use(async session => {
  const storage = client.Files(session.getId()!);
  const report = new Blob([new Uint8Array(await readFile('report.pdf'))]);
  await storage.upload(report, 'report.pdf');
  await storage.upload(report, 'quarterly_report.pdf');
  console.log((await storage.list({ source: 'user_upload' })).files);
  return await session.status();
});

import assert from 'node:assert/strict';
const storage = client.Files(status.session_id);
const { files } = await storage.list({ source: 'user_upload' });
try {
  assert.deepEqual(files.map(file => file.filename).sort(), ['quarterly_report.pdf', 'report.pdf']);
  for (const file of files) {
    assert.deepEqual(Buffer.from(await (await storage.download(file.id)).arrayBuffer()), await readFile('report.pdf'));
  }
} finally {
  for (const file of files) await storage.delete(file.id);
}
export { status };
