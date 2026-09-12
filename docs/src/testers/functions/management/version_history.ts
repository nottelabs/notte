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

const matched = functions.filter(fn => fn.function_id === process.env.NOTTE_FUNCTION_ID);
if (matched.length !== 1) throw new Error('Owned function missing from history');
const results = [matched[0].versions.length > 0, matched[0].versions.includes(matched[0].latest_version)];
export { results };
