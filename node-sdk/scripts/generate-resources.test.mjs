import assert from 'node:assert/strict';
import fs from 'node:fs';
import { test } from 'node:test';
import ts from 'typescript';
import { generateResources as generateMappedResources, checkCoverage } from './generate-resources.mjs';

const naming = JSON.parse(fs.readFileSync(new URL('../../openapi/resources.json', import.meta.url), 'utf8'));
const registry = new Map(Object.entries(naming).map(([id, entry]) => [id.replace(/^_+/, '').replace(/_([a-z])/g, (_, c) => c.toUpperCase()), entry]));
registry.set('sessionExample', { resource: 'sessions', method: 'example' });
registry.set('sessionList', { resource: 'sessions', method: 'list' });
const generateResources = (sdk, types) => generateMappedResources(sdk, types, registry);
test('rejects spec operations without an explicit mapping or exclusion', () => {
  assert.throws(() => checkCoverage({ paths: { '/new': { get: { operationId: 'unknown' } } } }), /Unmapped operation: unknown/);
});

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

test('rejects aliases that would replace another method', () => {
  const generate = (entries, names) => generateMappedResources(names.map(sdk).join('\n'), data(`url: '/sessions';`), new Map(entries));
  // An alias targeting a method another operation already emitted.
  assert.throws(() => generate([
    ['sessionList', { resource: 'sessions', method: 'list' }],
    ['sessionExample', { resource: 'sessions', method: 'example', aliases: [{ resource: 'sessions', method: 'list' }] }],
  ], ['sessionList', 'sessionExample']), /collision: sessions\.list/);
  // Two aliases with the same target.
  assert.throws(() => generate([
    ['sessionList', { resource: 'sessions', method: 'list', aliases: [{ resource: 'sessions', method: 'all' }] }],
    ['sessionExample', { resource: 'sessions', method: 'example', aliases: [{ resource: 'sessions', method: 'all' }] }],
  ], ['sessionList', 'sessionExample']), /collision: sessions\.all/);
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


test('spec-owned agent operations stay outside client resources while sessions remain callable', async () => {
  const read = file => fs.readFileSync(new URL(`../src/lib/client/${file}`, import.meta.url), 'utf8');
  const source = read('sdk.gen.ts');
  assert.match(source, /export const agentStart\b/);
  const generated = generateResources(source, read('types.gen.ts'));
  const js = ts.transpile(generated, { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 });
  const requests = [];
  const exports = {};
  const client = {};
  new Function('require', 'exports', js)(() => ({ sessionStatus: async options => {
    requests.push(options);
    return { data: { session_id: options.path.session_id } };
  } }), exports);
  const resources = exports.createResources(client, () => 'bound-key');
  assert.equal('agents' in resources, false);
  assert.deepEqual(await resources.sessions.status('session'), { session_id: 'session' });
  assert.equal(requests[0].client, client);
});

test('preserves run metadata request options before its new payload query', async () => {
  const generated = generateResources(sdk('functionRunGetMetadata'), data(`
    path: { function_id: string; run_id: string };
    headers?: { 'x-notte-request-origin'?: string };
    query?: { payload_mode?: 'inline' | 'references' };
    url: '/functions/{function_id}/runs/{run_id}';
  `));
  const js = ts.transpile(generated, { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 });
  const requests = [];
  const exports = {};
  new Function('require', 'exports', js)(() => ({ functionRunGetMetadata: async options => {
    requests.push(options);
    return { data: 'result' };
  } }), exports);
  const { runGetMetadata } = exports.createResources({}, () => 'bound-key').functions;
  const signal = new AbortController().signal;
  const headers = { 'x-notte-request-origin': 'custom-origin' };
  assert.equal(await runGetMetadata('function', 'run', { signal, headers }), 'result');
  await runGetMetadata('function', 'run', { signal, headers }, { payload_mode: 'references' });
  for (const request of requests) {
    assert.equal(request.signal, signal);
    assert.deepEqual(request.headers, headers);
  }
  assert.equal(requests[0].query, undefined);
  assert.deepEqual(requests[1].query, { payload_mode: 'references' });
});
