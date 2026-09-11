// @sniptest filename=force_overwrite.ts
// @sniptest show=15-16
import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();
const fixtureStorage = client.FileStorage();
const status = await client.Session({ storage: fixtureStorage }).use(async session => {
  const uploaded = await fixtureStorage.upload('file.pdf');
  try {
    const sessionId = fixtureStorage.sessionId;
    const fileId = uploaded.id;
    await mkdir('downloads', { recursive: true });
    await writeFile('downloads/file.pdf', 'old contents');

    const storage = client.FileStorage(sessionId);
    await storage.download(fileId, './downloads', { force: true });

    assert.deepEqual(await readFile('downloads/file.pdf'), await readFile('file.pdf'));
    return await session.status();
  } finally {
    await fixtureStorage.delete(uploaded.id);
  }
});
export { status };
