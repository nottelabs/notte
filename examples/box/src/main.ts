import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { NotteClient } from 'notte-sdk';
import { chromium } from 'playwright-core';

export async function capturePage() {
  return new NotteClient().Session({ max_duration_minutes: 3, proxies: false }).use(async session => {
    try {
      const browser = await chromium.connectOverCDP(await session.cdpUrl());
      try {
        const page = await browser.contexts()[0].newPage();
        await page.goto('https://example.com', { waitUntil: 'domcontentloaded', timeout: 30_000 });
        return { image: await page.screenshot({ fullPage: true }), sessionId: session.getId()! };
      } finally { await browser.close(); }
    } catch {
      throw new Error('Could not capture the hosted page');
    }
  });
}

export async function uploadCapture(image: Buffer, sessionId: string, token: string, folderId: string, fetcher: typeof fetch = fetch) {
  try {
    const form = new FormData();
    const name = `notte-${sessionId}.png`;
    form.append('attributes', JSON.stringify({ name, parent: { id: folderId } }));
    form.append('file', new Blob([new Uint8Array(image)], { type: 'image/png' }), name);
    const headers = { Authorization: `Bearer ${token}` };
    const uploaded = await fetcher('https://upload.box.com/api/2.0/files/content', {
      method: 'POST', headers, body: form, signal: AbortSignal.timeout(60_000),
    });
    if (!uploaded.ok) throw new Error('Box upload failed');
    const fileId = (await uploaded.json()).entries[0].id as string;
    const metadata = await fetcher(`https://api.box.com/2.0/files/${encodeURIComponent(fileId)}?fields=id,size,sha1`, {
      headers, signal: AbortSignal.timeout(30_000),
    });
    if (!metadata.ok) throw new Error('Box verification failed');
    const stored = await metadata.json();
    if (stored.size !== image.length || stored.sha1 !== createHash('sha1').update(image).digest('hex')) {
      throw new Error('Box content verification failed');
    }
    return { box_file_id: fileId, session_id: sessionId };
  } catch {
    throw new Error('Could not upload and verify the Box capture');
  }
}

export async function main() {
  const token = process.env.BOX_ACCESS_TOKEN;
  if (!token) throw new Error('Set BOX_ACCESS_TOKEN');
  const { image, sessionId } = await capturePage();
  return uploadCapture(image, sessionId, token, process.env.BOX_FOLDER_ID ?? '0');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) console.log(await main());
