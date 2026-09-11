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

test('navigation and generated reference links resolve; only supporting types and encryption are hidden', () => {
  const listed = new Set();
  const walk = node => {
    if (typeof node === 'string') listed.add(`${node}.mdx`);
    else if (Array.isArray(node)) node.forEach(walk);
    else node.pages?.forEach(walk);
  };
  walk(actual.navigation);
  for (const name of listed) assert.ok(actual.pages.has(name), `Missing navigation page: ${name}`);
  for (const name of actual.pages.keys()) {
    if (!listed.has(name)) assert.match(name, /\/types\/|\/encryption\/|\/manual\/encryption\.mdx$/);
  }
  for (const [name, content] of actual.pages) {
    for (const [, link] of content.matchAll(/\]\(\/(typescript-sdk-reference\/[^)#]+)(?:#[^)]*)?\)/g)) {
      assert.ok(actual.pages.has(`${link}.mdx`), `${name} links to missing ${link}`);
    }
  }
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
