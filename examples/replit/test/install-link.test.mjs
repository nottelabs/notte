import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { installLink } from '../install-link.mjs';

test('install link uses the official Replit shape and contains no authentication material', async () => {
  const url = new URL(await installLink());
  assert.equal(url.origin + url.pathname, 'https://replit.com/integrations');
  assert.deepEqual(JSON.parse(Buffer.from(url.searchParams.get('mcp'), 'base64').toString()), {
    displayName: 'Notte', baseUrl: 'https://api.notte.cc/mcp',
  });
});

test('the guide uses the current generated install link', async () => {
  const guide = await readFile(new URL('../../../docs/src/integrations/replit.mdx', import.meta.url), 'utf8');
  assert.ok(guide.includes(`href="${await installLink()}"`));
});
