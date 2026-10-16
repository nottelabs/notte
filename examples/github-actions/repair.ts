import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { NotteClient } from 'notte-sdk';

type Entry = { selector: string; role: 'link' | 'button'; name: string };
type Document = { url: string; selectors: Record<string, Entry> };

function readMap(source: Buffer): Document {
  if (source.length > 65_536) throw new Error('Selector map exceeds 64 KiB');
  const value = JSON.parse(source.toString('utf8'));
  if (!value || Array.isArray(value) || Object.keys(value).sort().join(',') !== 'selectors,url') throw new Error('Expected url and selectors');
  const url = new URL(value.url);
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) throw new Error('Use an HTTP(S) page URL without credentials');
  if (!value.selectors || Array.isArray(value.selectors) || Object.keys(value.selectors).length < 1 || Object.keys(value.selectors).length > 20) throw new Error('Provide 1-20 selectors');
  for (const [key, entry] of Object.entries(value.selectors) as [string, Entry][]) {
    if (!/^[a-zA-Z0-9_-]{1,64}$/.test(key) || !entry || Object.keys(entry).sort().join(',') !== 'name,role,selector'
      || !['link', 'button'].includes(entry.role) || typeof entry.name !== 'string' || !entry.name || entry.name.length > 256
      || typeof entry.selector !== 'string' || !entry.selector || entry.selector.length > 2048) throw new Error('Invalid selector entry');
  }
  return value;
}

export async function repair(source: Buffer, options: { fixtureHtml?: string; fixtureRedirect?: string; fixtureLateRedirect?: string; signal?: AbortSignal } = {}) {
  const map = readMap(source);
  const signal = AbortSignal.any([AbortSignal.timeout(90_000), ...(options.signal ? [options.signal] : [])]);
  let sessionId = 'unallocated';
  let stage = 'claim';
  try {
    return await new NotteClient().Session({ max_duration_minutes: 3 }).use(async (browser) => {
      sessionId = browser.getId()!;
      let page: Awaited<ReturnType<typeof browser.page>> | undefined;
      const abort = () => { void page?.close().catch(() => {}); };
      signal.addEventListener('abort', abort, { once: true });
      try {
        signal.throwIfAborted();
        page = await browser.page();
        signal.throwIfAborted();
        const expectedOrigin = new URL(map.url).origin;
        let changedOrigin = false;
        page.on('framenavigated', (frame) => {
          if (frame === page!.mainFrame() && new URL(frame.url()).origin !== expectedOrigin) {
            changedOrigin = true; stage = 'origin';
          }
        });
        await page.route('**/*', async (route) => {
          const request = route.request();
          if (request.isNavigationRequest() && request.frame() === page!.mainFrame() && new URL(request.url()).origin !== expectedOrigin) {
            changedOrigin = true; stage = 'origin';
            await route.abort();
          } else await route.continue();
        });
        const checkOrigin = () => {
          if (changedOrigin || new URL(page!.url()).origin !== expectedOrigin) throw new Error('Navigation changed origin');
        };
        if (options.fixtureRedirect) await page.route(map.url, (route) => route.fulfill({ status: 302, headers: { location: options.fixtureRedirect! }, body: '' }));
        stage = 'navigation';
        await page.goto(map.url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
        stage = 'origin';
        checkOrigin();
        stage = 'DOM';
        if (options.fixtureHtml !== undefined) await page.setContent(options.fixtureHtml);
        if (options.fixtureLateRedirect) {
          const blocked = page.waitForEvent('requestfailed');
          await page.evaluate((url) => { location.href = url; }, options.fixtureLateRedirect);
          await blocked;
        }
        stage = 'origin'; checkOrigin(); stage = 'DOM';
        const changes = [];
        for (const [key, entry] of Object.entries(map.selectors)) {
          signal.throwIfAborted();
          const target = page.getByRole(entry.role, { name: entry.name, exact: true });
          await target.first().waitFor({ state: 'attached', timeout: 5_000 });
          if (await target.count() !== 1) throw new Error('Expected exactly one semantic target');
          let valid = false;
          try { valid = await page.locator('css=' + entry.selector).count() === 1 && await target.evaluate((el, selector) => el.matches(selector), entry.selector); }
          catch { /* An invalid old CSS selector can still be repaired. */ }
          if (valid) continue;
          const after = await target.evaluate((el) => {
            if (el.id && el.id.length <= 128) return `${el.localName}#${CSS.escape(el.id)}`;
            const href = el.getAttribute('href');
            if (!href || href.length > 500) return null;
            const url = new URL(href, document.baseURI);
            if (!['http:', 'https:'].includes(url.protocol) || url.search || url.hash || url.username || url.password) return null;
            return `${el.localName}[href="${CSS.escape(href)}"]`;
          });
          if (!after || await page.locator('css=' + after).count() !== 1 || !await target.evaluate((el, selector) => el.matches(selector), after)) throw new Error('No unique stable replacement');
          changes.push({ key, before: entry.selector, after });
        }
        signal.throwIfAborted();
        stage = 'origin'; checkOrigin();
        return { version: 1, source_sha256: createHash('sha256').update(source).digest('hex'), session_id: sessionId, changes };
      } catch {
        throw new Error(`Selector repair ${signal.aborted ? 'cancelled' : 'refused'}: ${stage} (session ${sessionId})`);
      } finally { signal.removeEventListener('abort', abort); }
    });
  } catch { throw new Error(`Selector repair ${signal.aborted ? 'cancelled' : 'refused'}: ${stage} (session ${sessionId})`); }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const controller = new AbortController();
  let interruptedCode = 0;
  const interrupt = () => { interruptedCode = 130; controller.abort(); };
  const terminate = () => { interruptedCode = 143; controller.abort(); };
  process.on('SIGINT', interrupt); process.on('SIGTERM', terminate);
  try {
    const result = await repair(await readFile(new URL('./selectors.json', import.meta.url)), { signal: controller.signal });
    await writeFile(new URL('./proposal.json', import.meta.url), JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify({ session_id: result.session_id, changed: result.changes.length }));
  } catch (error) { console.error(error instanceof Error ? error.message : 'Selector repair failed'); process.exitCode = interruptedCode || 1; }
  finally { process.off('SIGINT', interrupt); process.off('SIGTERM', terminate); }
}
