import assert from 'node:assert/strict';
import fs from 'node:fs';
import { test } from 'node:test';
import ts from 'typescript';
import { generateResources } from './generate-resources.mjs';

const sdk = name => `export const ${name} = (options: Options<ExampleData, true>) => client.get(options);`;
const data = fields => `export type ExampleData = { ${fields} };`;

test('generates positional path arguments in URL order and forwards typed bodies', () => {
  const generated = generateResources(sdk('sessionExample'), data(`
    path: { file_id: string; session_id: string }; body: Upload;
    query?: { overwrite?: boolean }; url: '/sessions/{session_id}/files/{file_id}';
  `));
  assert.match(generated, /example: async \(sessionId:.*fileId:.*body:.*query:/);
  assert.match(generated, /path: \{ "session_id": sessionId, "file_id": fileId \}/);
  assert.match(generated, /throwOnError: true/);
  assert.match(generated, /return response.data/);
});

test('required query and optional body retain valid argument ordering', () => {
  const generated = generateResources(sdk('sessionExample'), data(`
    body?: Payload; query: { required: string }; path?: never; url: '/sessions/example';
  `));
  assert.match(generated, /body: Types.ExampleData\['body'\], query:/);
});

test('requires caller headers without moving existing path/body/query arguments', async () => {
  const generated = generateResources(sdk('sessionExample'), data(`
    path: { session_id: string }; body: Payload; query?: { update_metadata?: boolean };
    headers: { 'idempotency-key': string; 'x-notte-api-key': string };
    url: '/sessions/{session_id}/payments';
  `));
  assert.match(generated, /sessionId:.*body:.*query:.*requestOptions: ResourceRequestOptions & \{ headers: Omit<NonNullable<Types.ExampleData\['headers'\]>, 'x-notte-api-key'> \}\) =>/);
  // Execute the generated adapter with a stub operation, not a payment request.
  const js = ts.transpile(generated, { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 });
  let request;
  const exports = {};
  new Function('require', 'exports', js)(() => ({ sessionExample: async options => {
    request = options;
    return { data: 'result' };
  } }), exports);
  const client = {};
  const result = await exports.createResources(client, () => 'bound-key').sessions.example(
    'session', { amount: 1 }, undefined,
    { headers: { 'idempotency-key': 'same-key-on-retry', 'x-notte-api-key': 'override' } },
  );
  assert.equal(result, 'result');
  assert.equal(request.client, client);
  assert.deepEqual(request.headers, { 'idempotency-key': 'same-key-on-retry', 'x-notte-api-key': 'bound-key' });
});

test('optional headers remain optional and authentication-only methods keep their signature', () => {
  const optional = generateResources(sdk('sessionExample'), data(`
    headers?: { custom?: string }; url: '/sessions/example';
  `));
  assert.match(optional, /headers\?: Omit<.*\} = \{\}/);
  const bound = generateResources(sdk('sessionExample'), data(`
    headers: { 'x-notte-api-key': string }; url: '/sessions/example';
  `));
  assert.match(bound, /requestOptions: ResourceRequestOptions = \{\}/);
  assert.match(bound, /headers: \{ 'x-notte-api-key': getApiKey\(\) \}/);
});

test('rejects method collisions', () => {
  assert.throws(() => generateResources(`${sdk('sessionList')}\n${sdk('listSessions')}`, data(`url: '/sessions';`)), /collision/);
});

test('rejects path names that would shadow the bound client', () => {
  assert.throws(() => generateResources(sdk('sessionExample'), data(`
    path: { client: string }; url: '/sessions/{client}';
  `)), /Unsafe path parameter names/);
});

test('rejects missing schemas and empty output', () => {
  assert.throws(() => generateResources(sdk('sessionExample'), ''), /Missing operation data/);
  assert.throws(() => generateResources('', ''), /No resource operations/);
});

test('checked-in output is reproducible from the checked-in OpenAPI-derived SDK', () => {
  const read = file => fs.readFileSync(new URL(`../src/${file}`, import.meta.url), 'utf8');
  assert.equal(generateResources(read('lib/client/sdk.gen.ts'), read('lib/client/types.gen.ts')), read('resources.gen.ts'));
});
