import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

export async function installLink() {
  const server = JSON.parse(await readFile(new URL('./server.json', import.meta.url), 'utf8'));
  return `https://replit.com/integrations?mcp=${encodeURIComponent(Buffer.from(JSON.stringify(server)).toString('base64'))}`;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) console.log(await installLink());
