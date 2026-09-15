// @sniptest filename=deployment_options.ts
// @sniptest show=1-10
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const fn = client.NotteFunction({
  path: 'my_function.py',
  name: 'My Function', // Display name
  description: 'What this function does', // Description
  shared: false, // Private by default
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
