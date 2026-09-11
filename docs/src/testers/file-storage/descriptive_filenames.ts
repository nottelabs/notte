// @sniptest filename=descriptive_filenames.ts
// @sniptest show=19-29
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { NotteClient, RemoteFileStorage, sessionStatus, type SessionResponse } from 'notte-sdk';

// Record each successful upload before any subsequent request can fail.
const ownedUploads: Array<{ storage: RemoteFileStorage; id: string }> = [];
const originalUpload = RemoteFileStorage.prototype.upload;
RemoteFileStorage.prototype.upload = async function (...args) {
  const uploaded = await originalUpload.apply(this, args);
  ownedUploads.push({ storage: this, id: uploaded.id });
  status = (await sessionStatus({
    client: new NotteClient().getClient(), path: { session_id: this.sessionId }, throwOnError: true,
  })).data;
  return uploaded;
};
let status: SessionResponse;
const primaryErrors: unknown[] = [];
try {
  const { NotteClient } = await import('notte-sdk');

  const client = new NotteClient();
  const now = new Date();
  const date = [now.getFullYear(), now.getMonth() + 1, now.getDate()].map(n => String(n).padStart(2, '0')).join('');
  const time = [now.getHours(), now.getMinutes(), now.getSeconds()].map(n => String(n).padStart(2, '0')).join('');
  const timestamp = `${date}_${time}`;
  const storage = client.FileStorage();
  await client.Session({ storage }).use(async session => {
    await storage.upload('report.pdf', `report_${timestamp}.pdf`);
  });

  const { files } = await storage.list({ source: 'user_upload' });
  assert.deepEqual(files.map(file => file.filename).sort(), [`report_${timestamp}.pdf`]);
  for (const file of files) {
    assert.deepEqual(Buffer.from(await (await storage.downloadBlob(file.id)).arrayBuffer()), await readFile('report.pdf'));
  }
} catch (error) {
  primaryErrors.push(error);
  throw error;
} finally {
  RemoteFileStorage.prototype.upload = originalUpload;
  const cleanup = await Promise.allSettled(ownedUploads.map(file => file.storage.delete(file.id)));
  const errors = cleanup.filter(result => result.status === 'rejected').map(result => result.reason);
  if (errors.length) throw new AggregateError([...primaryErrors, ...errors], 'Example file cleanup failed');
}
export { status };
