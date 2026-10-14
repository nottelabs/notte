// @sniptest filename=version_history.ts
// @sniptest show=1-11
import { NotteClient } from 'notte-sdk';

const client = new NotteClient();

const functions = await client.functions.list();

for (const fn of functions) {
  console.log(`Function: ${fn.name}`);
  console.log(`Versions: ${fn.versions.join(', ')}`);
  console.log(`Latest: ${fn.latest_version}`);
}

// Other runs create functions in the same account at the same time, so this run's function
// may not be on the first page: page through the full list until it shows up.
let matched = functions.filter(fn => fn.function_id === process.env.NOTTE_FUNCTION_ID);
for (let page = 1; matched.length === 0; page++) {
  const batch = await client.functions.list({ page, page_size: 100 });
  matched = batch.filter(fn => fn.function_id === process.env.NOTTE_FUNCTION_ID);
  if (batch.length < 100) break;
}
if (matched.length !== 1) throw new Error('Owned function missing from history');
const results = [matched[0].versions.length > 0, matched[0].versions.includes(matched[0].latest_version)];
export { results };
