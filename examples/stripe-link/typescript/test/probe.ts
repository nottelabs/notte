import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import Link from '@stripe/link-sdk';
import { runDemo } from '../src/demo.ts';

const fixture = JSON.parse(readFileSync(new URL('../../test-card.json', import.meta.url), 'utf8'));
const reject = process.argv[2] === 'reject';
let calls = 0;
const fetchMock: typeof fetch = async (input, options) => {
  assert.equal(options?.method, 'GET');
  assert.equal(new URL(String(input)).searchParams.get('include'), 'card');
  calls++;
  return reject ? Response.json({ error: { message: 'PRIVATE_FIXTURE_BODY' } }, { status: 401 }) : Response.json(fixture);
};
runDemo(new Link({ accessToken: 'test-link-token', fetch: fetchMock })).then(result => {
  assert.equal(calls, 1);
  console.log(JSON.stringify(result));
}).catch(error => {
  console.error(error.message);
  process.exitCode = 1;
});
