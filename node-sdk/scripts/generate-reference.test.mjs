import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { compile } from '@mdx-js/mdx';
import { createReference, replaceNavigation, syncReference } from './generate-reference.mjs';

let fixture, generated, actual;
before(() => {
  fixture = mkdtempSync(resolve(tmpdir(), 'notte-reference-test-'));
  mkdirSync(resolve(fixture, 'src'));
  writeFileSync(resolve(fixture, 'tsconfig.json'), JSON.stringify({ compilerOptions: { strict: true, target: 'ES2022', module: 'ESNext', types: [], noEmit: true } }));
  writeFileSync(resolve(fixture, 'src/index.ts'), `
type Base = { /** Number of pixels. */ width: number; hidden: boolean };
export interface Options extends Omit<Base, 'hidden'> {
  /** @deprecated Use width. */ oldWidth?: number;
}
/** Session with <tags> and {expressions}. */
export class Session {
  private internalState = 0;
  protected hiddenMethod(): void {}
  /** @internal */ internal(): void {}
  #privateField = 0;
  constructor(options: Options = { width: 800 }) {}
  /** Start the session. @param url Destination URL. */
  start(url: string): Promise<string>;
  start(url: number): Promise<number>;
  start(url: string | number): Promise<string | number> { return Promise.resolve(url); }
  /** @deprecated Use start. */
  old(): void {}
  get id(): string { return 'id'; }
  static version(): string { return '1'; }
  [Symbol.asyncIterator](): AsyncGenerator<Session> { throw new Error(); }
}
class NotExported { visible(): void {} }
`);
  generated = createReference(fixture);
  actual = createReference();
});
after(() => rmSync(fixture, { recursive: true, force: true }));

test('discovers exported public API, preserves overloads, excludes implementations and internals', () => {
  const page = generated.pages.get('typescript-sdk-reference/session/start.mdx');
  assert.match(page, /Session.start\(url: string\): Promise<string>/);
  assert.match(page, /Session.start\(url: number\): Promise<number>/);
  assert.doesNotMatch(page, /url: string \| number/);
  assert.match(page, /Destination URL/);
  const all = [...generated.pages.values()].join('\n');
  for (const hidden of ['internalState', 'privateField', 'hiddenMethod', 'NotExported', 'Session.internal']) assert.ok(!all.includes(hidden), hidden);
  assert.match(all, /&lt;tags&gt; and &#123;expressions&#125;/);
  assert.match(all, /static Session.version/);
  assert.match(all, /\*\*deprecated:\*\*/);
  assert.ok(generated.pages.has('typescript-sdk-reference/session/symbol-asynciterator.mdx'));
});

test('renders defaults, optional properties and inherited mapped fields', () => {
  const session = generated.pages.get('typescript-sdk-reference/manual/session.mdx');
  assert.match(session, /Default:\n\n```typescript\n\{ width: 800 \}/);
  const options = generated.pages.get('typescript-sdk-reference/types/options.mdx');
  assert.match(options, /body="width" type=\{"number"\} required/);
  assert.match(options, /body="oldWidth" type=\{"number \| undefined"\}>/);
  assert.doesNotMatch(options, /body="hidden"/);
});

test('all generated MDX compiles, including generics, JSX-sensitive JSDoc and parameter fields', async () => {
  for (const [name, content] of [...generated.pages, ...actual.pages]) {
    // Frontmatter is consumed separately by Mintlify, not the MDX compiler.
    await assert.doesNotReject(() => compile(content.replace(/^---\n[\s\S]*?\n---\n/, '')), name);
  }
});

test('real SDK output covers factories, aliases and inherited session options without local paths', () => {
  assert.ok(actual.pages.has('typescript-sdk-reference/function/createrun.mdx'));
  assert.ok(actual.pages.has('typescript-sdk-reference/function/getrun.mdx'));
  assert.match(actual.pages.get('typescript-sdk-reference/function/retrieve.mdx'), /Compatibility alias for getRun/);
  assert.match(actual.pages.get('typescript-sdk-reference/types/sessionoptions.mdx'), /body="idle_timeout_minutes"/);
  assert.ok(actual.pages.has('typescript-sdk-reference/client/session.mdx'));
  for (const content of actual.pages.values()) assert.doesNotMatch(content, /import\("\/|\/Users\/|\/private\/tmp\//);
});

test('navigation and generated reference links resolve; supporting APIs can remain hidden', () => {
  const listed = new Set();
  const walk = node => {
    if (typeof node === 'string') listed.add(`${node}.mdx`);
    else if (Array.isArray(node)) node.forEach(walk);
    else node.pages?.forEach(walk);
  };
  walk(actual.navigation);
  for (const name of listed) assert.ok(actual.pages.has(name), `Missing navigation page: ${name}`);
  for (const name of actual.pages.keys()) {
    if (!listed.has(name) && !actual.pages.get(name).includes('**deprecated:**')) assert.match(name, /\/types\/|\/encryption\/|\/manual\/encryption\.mdx$|\/symbol-asynciterator\.mdx$|\/function\/getfunctionid\.mdx$|\/session\/getid\.mdx$/);
  }
  for (const [name, content] of actual.pages) {
    for (const [, link] of content.matchAll(/\]\(\/(typescript-sdk-reference\/[^)#]+)(?:#[^)]*)?\)/g)) {
      assert.ok(actual.pages.has(`${link}.mdx`), `${name} links to missing ${link}`);
    }
  }
});

test('deprecated methods remain documented but are excluded from navigation and overview links', () => {
  assert.ok(!JSON.stringify(generated.navigation).includes('/session/old'));
  assert.match(generated.pages.get('typescript-sdk-reference/session/old.mdx'), /\*\*deprecated:\*\*/);
  assert.ok(!JSON.stringify(actual.navigation).includes('/function/retrieve'));
  assert.ok(JSON.stringify(actual.navigation).includes('/function/getrun'));
  assert.match(actual.pages.get('typescript-sdk-reference/function/retrieve.mdx'), /Use getRun\(\) instead/);
  assert.ok(!actual.pages.get('typescript-sdk-reference/manual/function.mdx').includes('[retrieve]'));
});

test('feature landing pages use factories and method navigation follows user tasks', () => {
  for (const [name, factory] of Object.entries({ session: 'Session', agent: 'Agent', function: 'NotteFunction', vault: 'Vault', persona: 'Persona', files: 'Files' })) {
    const content = actual.pages.get(`typescript-sdk-reference/manual/${name}.mdx`);
    assert.match(content, /^---\ntitle: "Get started"/);
    assert.ok(content.includes(`client.${factory}(`));
    assert.ok(content.indexOf(`client.${factory}(`) < content.indexOf('Direct constructor reference'));
  }
  const core = actual.navigation.pages.find(group => group.group === 'Core Features');
  assert.equal(core.pages[0], 'typescript-sdk-reference/client/scrape');
  const session = core.pages.find(group => group.group === 'Session');
  assert.deepEqual(session.pages.slice(0, 6), ['manual/session', 'session/start', 'session/stop', 'session/observe', 'session/execute', 'session/scrape'].map(path => `typescript-sdk-reference/${path}`));
  for (const method of ['getid', 'getresponse', 'issessionactive', 'symbol-asynciterator']) assert.ok(!session.pages.includes(`typescript-sdk-reference/session/${method}`));
  assert.ok(!JSON.stringify(actual.navigation).includes('symbol-asynciterator'));
  const debug = actual.navigation.pages.find(group => group.group === 'Debug');
  assert.equal(debug.pages[0].group, 'Debug Methods');
  assert.ok(debug.pages[0].pages.includes('typescript-sdk-reference/session/getresponse'));
  assert.ok(!JSON.stringify(actual.navigation).includes('/getfunctionid'));
  assert.ok(!JSON.stringify(actual.navigation).includes('/getid'));
  assert.ok(JSON.stringify(actual.navigation).includes('/getrun'));
  assert.ok(!actual.pages.get('typescript-sdk-reference/manual/function.mdx').includes('[getFunctionId]'));
  for (const path of ['session/start', 'agent/run', 'function/createrun', 'vault/addcredentials', 'persona/emails', 'files/upload']) {
    const title = actual.pages.get(`typescript-sdk-reference/${path}.mdx`).match(/^title: "(.*)"/m)[1];
    assert.ok(!title.includes('.'), `Method title must be unqualified: ${title}`);
  }
});

test('Session guide reuses its tested snippet, usage cards, and all generated option fields', () => {
  const page = actual.pages.get('typescript-sdk-reference/manual/session.mdx');
  const snippet = readFileSync(new URL('../../docs/src/snippets/sessions/index.mdx', import.meta.url), 'utf8');
  const code = snippet.match(/^```typescript[^\n]*\n([\s\S]*?)^```/m)[1].trimEnd();
  assert.ok(page.includes('```typescript\n' + code + '\n```'));
  const source = readFileSync(new URL('../../docs/src/testers/sessions/index.ts', import.meta.url), 'utf8');
  assert.equal(code, source.replace(/^(?:\/\/ @sniptest[^\n]*\n)+/, '').trimEnd());
  assert.ok(page.indexOf('await client.Session') < page.indexOf('## Usage'));
  for (const method of ['scrape', 'observe', 'execute']) assert.ok(page.includes(`href="/typescript-sdk-reference/session/${method}"`));
  assert.match(page, /<CardGroup cols=\{3\}>/);
  const fields = text => [...text.matchAll(/<ParamField[\s\S]*?<\/ParamField>/g)].map(match => match[0]);
  assert.deepEqual(fields(page.split('<Accordion')[0]), fields(actual.pages.get('typescript-sdk-reference/types/sessionoptions.mdx')));
  assert.match(page, /body="open_viewer"/);
  assert.match(page, /body="idle_timeout_minutes"/);
  assert.doesNotMatch(page.split('<Accordion')[0], /body="options"|export \{|JSON.stringify/);
});

test('Node SDK mirrors Python categories and appears below Python in the sidebar', () => {
  assert.equal(actual.navigation.group, 'Node SDK');
  assert.deepEqual(actual.navigation.pages.map(group => group.group), ['Getting Started', 'Core Features', 'Tooling', 'Debug']);
  const categoryNames = category => actual.navigation.pages.find(group => group.group === category).pages
    .filter(page => typeof page === 'object').map(page => page.group);
  assert.ok(categoryNames('Getting Started').includes('Client'));
  assert.deepEqual(categoryNames('Core Features'), ['Session', 'Actions', 'Agent', 'Function']);
  assert.deepEqual(categoryNames('Tooling'), ['Vault', 'Persona', 'File Storage']);
  const actions = actual.navigation.pages.find(group => group.group === 'Core Features').pages.find(group => group.group === 'Actions');
  assert.ok(actions.pages.includes('typescript-sdk-reference/types/gotoaction'));
  assert.ok(actions.pages.includes('typescript-sdk-reference/types/clickactionoutput'));
  assert.ok(!actions.pages.includes('typescript-sdk-reference/types/actionspace'));
  assert.ok(!JSON.stringify(actual.navigation).includes('encryption'));
  const docs = JSON.parse(readFileSync(new URL('../../docs/src/docs.json', import.meta.url), 'utf8'));
  const navigation = JSON.stringify(docs.navigation);
  const python = navigation.indexOf('"group":"Python SDK"');
  const node = navigation.indexOf('"group":"Node SDK"');
  assert.ok(python >= 0 && node > python, 'Python SDK must appear before Node SDK');
  assert.ok(!navigation.includes('"group":"TypeScript SDK"'));
});

test('review regressions preserve complete summaries and accurate Node descriptions', () => {
  const page = path => actual.pages.get(`typescript-sdk-reference/${path}.mdx`);
  assert.match(page('manual/function'), /Returns the code, and writes it to `path` when one is provided\./);
  assert.match(page('manual/function'), /API returns an encrypted one/);
  assert.match(page('persona/get'), /## Returns\s+```typescript\nPromise<PersonaResponseWithInternalEmail>/);
  assert.match(page('persona/use'), /existing ID are retained/);
  assert.match(page('session/viewer'), /\*\*throws:\*\*[\s\S]*no viewer URL/);
  for (const name of ['apiagentstartrequest', 'scraperequest']) {
    assert.doesNotMatch(page(`types/${name}`), /Pydantic/);
    assert.match(page(`types/${name}`), /JSON Schema object/);
  }
  for (const name of ['listpersonasdata', 'personalistoptions']) {
    assert.doesNotMatch(page(`types/${name}`), /active sessions|return sessions|system sessions/);
    assert.match(page(`types/${name}`), /active personas/);
  }
  for (const name of ['checkactionoutput', 'clickactionoutput', 'credentialsdictinput', 'creditcarddictinput', 'selectdropdownoptionactionoutput', 'downloadfileactionoutput', 'smsresponse', 'fallbackfillactionoutput', 'fillactionoutput', 'uploadfileactionoutput', 'multifactorfillactionoutput', 'structureddatabasemodel']) {
    assert.doesNotMatch(page(`types/${name}`).split('```typescript')[0], /\n(?:CheckAction|ClickAction|CredentialsDict|CreditCardDict|SelectDropdownOptionAction|DownloadFileAction|SmsResponse|FallbackFillAction|FillAction|UploadFileAction|MultiFactorFillAction|StructuredData\[BaseModel\])\n/);
  }
  assert.doesNotMatch(page('types/cookie').split('## Fields')[1], /Httponly|Expirationdate|Hostonly|Samesite|Storeid|Partitionkey/);
  assert.match(page('vault/generatepassword'), /do not use this[\s\S]*security-sensitive/);
});

test('navigation replacement preserves unrelated Python navigation and formatting', () => {
  const input = '{\n  "navigation": [{"group": "SDK", "pages": ["sdk-reference/manual/session"]},\n  {"group": "Node SDK", "pages": []}]\n}\n';
  const replaced = replaceNavigation(input, generated.navigation);
  assert.ok(replaced.startsWith(input.split('{"group": "Node SDK"')[0]));
  assert.deepEqual(JSON.parse(replaced).navigation[0], JSON.parse(input).navigation[0]);
  assert.equal(replaceNavigation(replaced, generated.navigation), replaced);
  assert.throws(() => replaceNavigation('{}', generated.navigation), /Expected one/);
});

test('check is non-mutating and detects missing, edited and orphaned generated pages', () => {
  const output = resolve(fixture, 'docs');
  mkdirSync(output);
  writeFileSync(resolve(output, 'docs.json'), '{"group": "Node SDK", "pages": []}');
  assert.ok(syncReference(generated, output, true).length);
  syncReference(generated, output);
  assert.deepEqual(syncReference(generated, output, true), []);
  const name = 'typescript-sdk-reference/session/old.mdx';
  const original = readFileSync(resolve(output, name), 'utf8');
  writeFileSync(resolve(output, name), `${original}\nEdited\n`);
  assert.ok(syncReference(generated, output, true).includes(name));
  assert.match(readFileSync(resolve(output, name), 'utf8'), /Edited/);
  const orphan = 'typescript-sdk-reference/session/orphan.mdx';
  writeFileSync(resolve(output, orphan), original);
  assert.ok(syncReference(generated, output, true).includes(orphan));
  syncReference(generated, output);
  assert.deepEqual(syncReference(generated, output, true), []);
  writeFileSync(resolve(output, orphan), 'Manually maintained page');
  assert.throws(() => syncReference(generated, output), /unowned file/);
});

test('source changes update generated signatures without a separate documentation definition', () => {
  const path = resolve(fixture, 'src/index.ts');
  const source = readFileSync(path, 'utf8');
  writeFileSync(path, source.replace('old(): void {}', 'old(count = 2): void {}'));
  const updated = createReference(fixture);
  assert.notEqual(updated.pages.get('typescript-sdk-reference/session/old.mdx'), generated.pages.get('typescript-sdk-reference/session/old.mdx'));
  assert.match(updated.pages.get('typescript-sdk-reference/session/old.mdx'), /count\?: number/);
  writeFileSync(path, source);
});
