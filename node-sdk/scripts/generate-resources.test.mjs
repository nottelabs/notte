import assert from 'node:assert/strict';
import fs from 'node:fs';
import { test } from 'node:test';
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

test('unknown required headers fail rather than generating an unauthenticated call', () => {
  assert.throws(() => generateResources(sdk('sessionExample'), data(`
    headers: { custom: string }; url: '/sessions/example';
  `)), /Unbound required headers/);
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
