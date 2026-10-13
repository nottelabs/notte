// @sniptest filename=url_upload.ts
// @sniptest show=23-36
import assert from 'node:assert/strict';
import { Session, type SessionResponse } from 'notte-sdk';

let status: SessionResponse;
const originalExecute = Session.prototype.execute;
Session.prototype.execute = async function (...args) {
  const result = await originalExecute.apply(this, args);
  if (args[0].type === 'upload_file') {
    const page = await this.page();
    const uploaded = await page.locator('input[type="file"]').evaluate(async element => {
      const file = (element as HTMLInputElement).files![0];
      return { name: file.name, text: await file.text() };
    });
    const response = await fetch('https://test-resources-lovat.vercel.app/text1.txt');
    assert.ok(response.ok);
    assert.deepEqual(uploaded, { name: 'text1.txt', text: await response.text() });
    status = await this.status();
  }
  return result;
};

try {
  const { NotteClient } = await import('notte-sdk');

  const client = new NotteClient();

  await client.Session().use(async session => {
    await session.execute({
      type: 'goto', url: 'https://test-resources-lovat.vercel.app/upload_fixture.html',
    });
    await session.execute({
      type: 'upload_file',
      selector: 'input[type="file"]',
      file_path: 'https://test-resources-lovat.vercel.app/text1.txt',
    });
  });
} finally {
  Session.prototype.execute = originalExecute;
}
export { status };
