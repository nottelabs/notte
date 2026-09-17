// @sniptest filename=deploy_sdk.ts
// @sniptest show=1-14
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

// Deploy function
const fn = client.NotteFunction({
  path: 'scraper_function.py',
  name: 'Website Scraper',
  description: 'Scrapes data from websites',
});

const response = await fn.get();
console.log(`Function deployed: ${response.function_id}`);
console.log(`Version: ${response.latest_version}`);

let results: unknown[];
try {
  const metadata = await fn.get();
  const result = await fn.run({ url: 'https://example.com' }, { stream: false });
  if (result.status !== 'closed') throw new Error('Uploaded function did not complete');
  if (!metadata.versions.includes(metadata.latest_version)) throw new Error('Missing deployed version');
  results = [metadata.name, metadata.description, metadata.shared, result.result];
} finally {
  await fn.delete();
}
export { results };
