// @sniptest filename=attach_before_starting.ts
// @sniptest show=15-20
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { NotteClient, RemoteFileStorage, sessionStatus, type SessionResponse } from 'notte-sdk';

// Record each successful upload before any subsequent request can fail.
const ownedUploads: Array<{ storage: RemoteFileStorage; id: string }> = [];
const originalUpload = RemoteFileStorage.prototype.upload;
RemoteFileStorage.prototype.upload = async function (...args) {
  const uploaded = await originalUpload.apply(this, args);
  ownedUploads.push({ storage: this, id: uploaded.id });
  return uploaded;
};
let status: SessionResponse;
try {
  const client = new NotteClient();
  const storage = client.FileStorage();
  await client.Session({ storage }).use(async session => {
    // Storage is always available and scoped to the session.
    await storage.upload('file.pdf');
  });

  const { data: capturedStatus } = await sessionStatus({
    client: client.getClient(), path: { session_id: storage.sessionId }, throwOnError: true,
  });
  status = capturedStatus;
  const { files } = await storage.list({ source: 'user_upload' });
  assert.deepEqual(files.map(file => file.filename).sort(), ["file.pdf"]);
  for (const file of files) {
    assert.deepEqual(Buffer.from(await (await storage.downloadBlob(file.id)).arrayBuffer()), await readFile('file.pdf'));
  }
} finally {
  RemoteFileStorage.prototype.upload = originalUpload;
  const cleanup = await Promise.allSettled(ownedUploads.map(file => file.storage.delete(file.id)));
  const errors = cleanup.filter(result => result.status === 'rejected').map(result => result.reason);
  if (errors.length) throw new AggregateError(errors, 'Failed to delete uploaded example files');
}
export { status };
