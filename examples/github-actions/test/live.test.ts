import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { setTimeout as sleep } from 'node:timers/promises';
import { repair } from '../repair.ts';

const source = JSON.parse(await readFile(new URL('../selectors.json', import.meta.url), 'utf8'));
const cases: Record<string, string | undefined> = {
  repair: undefined, unchanged: undefined,
  missing: '<a id="other">Other</a>',
  ambiguous: '<a href="/a">Learn more</a><a href="/b">Learn more</a>',
  unstable: '<a role="link">Learn more</a>',
  collision: '<a id="duplicate" href="/a">Learn more</a><a id="duplicate" href="/b">Other</a>',
  navigation: undefined, redirect: undefined, cancel: undefined,
};

async function closed(id: string) {
  const deadline = Date.now() + 15_000;
  while (true) {
    const response = await fetch(`${process.env.NOTTE_API_URL ?? 'https://api.notte.cc'}/sessions/${id}`, {
      headers: { Authorization: `Bearer ${process.env.NOTTE_API_KEY!}` }, signal: AbortSignal.timeout(20_000),
    });
    assert.equal(response.status, 200);
    const row = await response.json() as { status: string };
    if (row.status === 'closed') return;
    assert.ok(Date.now() < deadline, `Owned browser ${id} remains active`);
    await sleep(500);
  }
}

for (const [mode, fixtureHtml] of Object.entries(cases)) {
  test(`real DOM ${mode} and owned browser cleanup`, { timeout: 110_000 }, async () => {
    const document = structuredClone(source);
    if (mode === 'unchanged') document.selectors.learn_more.selector = 'a';
    if (mode === 'navigation') document.url = 'https://notte-selector-missing.invalid';
    if (mode === 'redirect') document.url = 'https://notte-selector-fixture.invalid/start';
    const controller = new AbortController();
    if (mode === 'cancel') controller.abort(); // Claim still completes; the already-aborted callback must release it.
    const run = repair(Buffer.from(JSON.stringify(document)), { fixtureHtml, fixtureRedirect: mode === 'redirect' ? 'https://example.com' : undefined, signal: controller.signal });
    let id: string;
    if (['repair', 'unchanged'].includes(mode)) {
      const result = await run;
      id = result.session_id;
      assert.equal(result.changes.length, mode === 'unchanged' ? 0 : 1);
      if (result.changes.length) assert.match(result.changes[0].after!, /^a\[href="/);
    } else {
      try { await run; assert.fail('Expected refusal'); }
      catch (error) {
        assert.ok(error instanceof Error);
        assert.ok(!error.message.includes(process.env.NOTTE_API_KEY!));
        assert.ok(!error.message.includes('wss:'));
        if (mode === 'redirect') assert.ok(error.message.includes('origin'));
        id = error.message.match(/session ([a-f0-9-]{36})/)![1];
      }
    }
    await closed(id);
    console.log(`${mode}: owned browser ${id} independently closed`);
  });
}
