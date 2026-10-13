// @sniptest filename=deploy_function.ts
// @sniptest show=1-14
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

// Deploy function
const fn = client.NotteFunction({
  path: 'my_automation.py',
  name: 'Search Automation',
  description: 'Searches a website and extracts results',
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
