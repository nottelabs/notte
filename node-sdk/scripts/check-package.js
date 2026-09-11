// Exercise the package export map in both module formats without API calls.
const { execFileSync } = require('node:child_process');

for (const format of ['commonjs', 'module']) {
  const code = format === 'commonjs'
    ? "const sdk = require('notte-sdk'); const proxy = require('notte-sdk/proxy'); const next = require('notte-sdk/next');"
    : "import * as sdk from 'notte-sdk'; import * as proxy from 'notte-sdk/proxy'; import * as next from 'notte-sdk/next';";
  execFileSync(process.execPath, [
    `--input-type=${format}`, '-e',
    `${code} if (typeof sdk.NotteClient !== 'function' || !Object.keys(proxy).length || !Object.keys(next).length) process.exit(1);`,
  ], { cwd: require('node:path').resolve(__dirname, '..'), stdio: 'inherit' });
}
console.log('CommonJS and ESM package exports passed');
