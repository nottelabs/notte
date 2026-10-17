import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { setTimeout as sleep } from 'node:timers/promises';
import { NotteClient } from 'notte-sdk';
import { repair } from '../repair.ts';

const source = JSON.parse(await readFile(new URL('../fixtures/selectors.json', import.meta.url), 'utf8'));
const cases: Record<string, string | undefined> = {
  repair: undefined, unchanged: undefined,
  delayed: `<script>setTimeout(() => { document.body.innerHTML = '<a id="learn-more" href="/a">Learn more</a>'; }, 150)</script>`,
  id: '<a id="learn-more" href="/a">Learn more</a>',
  escaped_id: '<a id="learn:more" href="/a">Learn more</a>',
  late_redirect: undefined,
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

for (const hostname of ['bücher.invalid', 'xn--bcher-kva.invalid', 'faß.invalid', 'xn--fa-hia.invalid']) {
  test(`IDN ${hostname} preserves the intended origin`, { timeout: 110_000 }, async () => {
    const document = { ...structuredClone(source), url: `https://${hostname}/start` };
    const result = await repair(Buffer.from(JSON.stringify(document)), { fixtureNavigationHtml: '<a id="learn-more" href="/a">Learn more</a>' });
    await closed(result.session_id);
    console.log(`IDN ${hostname}: owned browser ${result.session_id} independently closed`);
    assert.equal(result.changes[0].after, 'a#learn-more');
  });
}

for (const suppressFrameEvent of [false, true]) {
  test(`IDN normalization refuses a different origin${suppressFrameEvent ? ' before a frame event' : ''}`, { timeout: 110_000 }, async (context) => {
    if (suppressFrameEvent) {
      const originalSession = NotteClient.prototype.Session;
      context.mock.method(NotteClient.prototype, 'Session', function (this: NotteClient, ...args: Parameters<typeof originalSession>) {
        const session = originalSession.apply(this, args);
        const originalPage = session.page.bind(session);
        context.mock.method(session, 'page', async (...pageArgs: Parameters<typeof originalPage>) => {
          const page = await originalPage(...pageArgs);
          // A failed redirect need not emit its error-page frame event before refusal.
          context.mock.method(page, 'on', new Proxy(page.on, {
            apply(target, receiver, args) {
              return args[0] === 'framenavigated' ? receiver : Reflect.apply(target, receiver, args);
            },
          }));
          return page;
        });
        return session;
      });
    }
    const document = { ...structuredClone(source), url: 'https://faß.invalid/start' };
    let id: string;
    let message: string;
    try {
      await repair(Buffer.from(JSON.stringify(document)), { fixtureRedirect: 'https://fass.invalid/start' });
      assert.fail('Expected origin refusal');
    } catch (error) {
      assert.ok(error instanceof Error);
      message = error.message;
      id = error.message.match(/session ([a-f0-9-]{36})/)![1];
    }
    await closed(id);
    console.log(`IDN foreign origin: owned browser ${id} independently closed`);
    assert.match(message, /refused: origin/);
  });
}

for (const [mode, fixtureHtml] of Object.entries(cases)) {
  test(`real DOM ${mode} and owned browser cleanup`, { timeout: 110_000 }, async () => {
    const document = structuredClone(source);
    if (mode === 'unchanged') document.selectors.learn_more.selector = 'a';
    if (mode === 'navigation') document.url = 'https://notte-selector-missing.invalid';
    if (mode === 'redirect') document.url = 'https://notte-selector-fixture.invalid/start';
    const controller = new AbortController();
    if (mode === 'cancel') controller.abort(); // Claim still completes; the already-aborted callback must release it.
    const run = repair(Buffer.from(JSON.stringify(document)), { fixtureHtml, fixtureLateRedirect: mode === 'late_redirect' ? 'https://www.iana.org' : undefined, fixtureRedirect: mode === 'redirect' ? 'https://example.com' : undefined, signal: controller.signal });
    let id: string;
    if (['repair', 'unchanged', 'id', 'escaped_id', 'delayed'].includes(mode)) {
      const result = await run;
      id = result.session_id;
      assert.equal(result.changes.length, mode === 'unchanged' ? 0 : 1);
      if (result.changes.length) {
        if (['id', 'escaped_id', 'delayed'].includes(mode)) assert.equal(result.changes[0].after, mode !== 'escaped_id' ? 'a#learn-more' : 'a#learn\\:more');
        else assert.match(result.changes[0].after!, /^a\[href="/);
      }
    } else {
      try { await run; assert.fail('Expected refusal'); }
      catch (error) {
        assert.ok(error instanceof Error);
        assert.ok(!error.message.includes(process.env.NOTTE_API_KEY!));
        assert.ok(!error.message.includes('wss:'));
        if (['redirect', 'late_redirect'].includes(mode)) assert.ok(error.message.includes('origin'));
        id = error.message.match(/session ([a-f0-9-]{36})/)![1];
      }
    }
    await closed(id);
    console.log(`${mode}: owned browser ${id} independently closed`);
  });
}
