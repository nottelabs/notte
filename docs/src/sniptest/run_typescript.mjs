// Execute the original example in the caller's isolated working directory.
import { pathToFileURL } from 'node:url';
import { register } from 'node:module';
register('./typescript-loader.mjs', import.meta.url);
const values = await import(pathToFileURL(process.argv[2]).href);
console.log(JSON.stringify(values));
