// @sniptest filename=private_function.ts
// @sniptest show=1-9
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const fn = client.NotteFunction({
  path: 'my_function.py',
  name: 'Private Automation',
  shared: false, // Private (default)
});

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
