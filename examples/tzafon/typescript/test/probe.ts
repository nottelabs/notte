import assert from 'node:assert/strict';
import Lightcone from '@tzafon/lightcone';
import { runDemo } from '../src/demo.ts';
import { CODE, wire } from './fixture.ts';

const { mock, requests } = wire(process.argv[2], true);
runDemo(new Lightcone({ apiKey: 'fixture-provider-key', baseURL: 'https://lightcone.invalid', fetch: mock, maxRetries: 0 }), CODE).then(result => { // pragma: allowlist secret
  assert.equal(requests.length, 3);
  console.log(JSON.stringify(result));
}).catch(error => {
  assert.equal(requests.length, 1);
  console.error(error.message);
  process.exitCode = 1;
});
