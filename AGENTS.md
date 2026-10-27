# Notte: agent guidance

Setup is in `docs/setup.md`; contribution rules are in `docs/CONTRIBUTING.md`.
Docs pages under `docs/src/` also follow `docs/src/.claude/CLAUDE.md`.

## Typing

- Don't add `object` or `Any` annotations. Use the real types, e.g.
  `RemoteSession` from `notte_sdk.endpoints.sessions` for a session.
  basedpyright does not flag these (`reportAny` is off), so review for them.
- Follow existing API patterns instead of inventing new ones. Methods with a
  `raise_on_failure` flag use `@overload` on `Literal[True]`/`Literal[False]`
  to type the return value; see `RemoteSession.scrape`.

## Tests

- Protected `main` requires the `tests` gate on an up-to-date branch. After
  rebasing, verify CI on the new head before calling a PR ready to merge.
- Never add `xfail`, `skip` or an ignore to make a failing test pass. Fix the
  cause, or stop and explain why it fails.
- CI's live LLM calls (`staging-and-live`) go through OpenRouter: the
  `OPENROUTER_API_KEY` secret as `NOTTE_LLM_API_KEY` with `google/...` model
  IDs. Don't point them at a provider's direct API key; the shared direct
  Gemini key hits rate limits. Only `llm-provider-matrix` tests direct routes.
- `make test` is the offline gate. `make test-live` runs tests marked
  `staging` or `live` and needs `NOTTE_API_KEY`; set `NOTTE_API_URL` to point
  the SDK at a different API.
- CDP transport tests keep real staging sessions and connections but serve page
  fixtures through Patchright routes, so navigation and screenshot coverage does
  not depend on third-party sites loading.
- README live CI uses the official HTTPS Ubuntu archive in the runner's
  `/etc/apt/apt-mirrors.txt`; the Azure mirror has stalled Chromium dependency
  installation before the examples could run.
- Browser settle regressions are in `tests/browser/test_execute_settle.py`
  and `tests/browser/test_settle_rules.py` and use a local server. Use the
  lockfile's Patchright environment: an older installed version can fail the
  tracker's `JSHandle` calls even when the locked version passes.
- Scroll fallback regressions in `tests/browser/test_controller_scroll.py` include
  clipping and overlays outside nested frames, and scaled iframe coordinates.
  Frame clips already include the viewport: skip the document's scrolling element
  and inline/contents ancestors, whose client boxes do not clip their contents.
- `BrowserWindow.page` can select a replacement automatically when its opener
  closes. Wait for a new tab independently of selection; its navigation request
  can also precede the context's `page` event.
  The driver can report a closed target from the click that closes its opener;
  accept that click only when a live replacement appears, and wait for it.
  When activating a tracked late tab, retain earlier tabs and their request trackers
  until selection succeeds. A tab closing during activation must not discard the
  surviving candidates or stop watching when none survive.
- A new-document `goto` tracks requests before its commit and waits for the destination
  within one navigation budget. Do not wait on the old document's tracker first:
  a commit after the 3 s settle cap must still get its remaining load wait.
  Hash-only gotos retain the current document's tracker before the URL changes,
  so delayed route rendering is still observed.
  Use the navigation response to identify a new document, rather than comparing
  URL spellings: the browser normalizes schemes, empty paths, hosts and ports.
  Goto tracker startup uses the existing 500 ms grace as its deadline; an
  unresponsive old page must not prevent navigation from starting.
  If startup expires before a hash goto, preserve the known URL change when
  tracking resumes so the existing render-wait rule still applies.
  Clear that same-document expectation when navigation destroys the tracker:
  a hash handler's redirect needs the destination's load and post-load waits.
- Native integration examples (`examples/*`, run by
  `scripts/ci_integration_examples.py`) install the local `node-sdk` with
  `npm install --no-save`. Don't add `--package-lock=false`: it ignores the
  example's lockfile, so a new upstream release can break CI.
- `evaluate_js` preserves RegExp results as JSON data (`{"r": {"p": source,
  "f": flags}}`), including complete patterns. Patchright 1.64.1 and Playwright
  1.64.0 compile native regex results into Python objects, so native evaluation is
  no longer the format oracle for regexes. Never compile page-controlled patterns
  during result conversion; test their JSON contract, output budgets, and shared
  containers explicitly.

## DOM build script

`packages/notte-browser/src/notte_browser/js/buildDomNode.js` reads elements through
its helpers (`getAttribute(element, name)`, `childrenOf(element)`,
`propertyOf(element, name)`, ...), never as `element.children`: a `<form>` exposes
its controls as properties named after their `name` or `id`, which hide the
form's own (`<input name="children">` makes `form.children` that input). The
same goes for `document.*` in the page's own world (`<img name="body">`).
`tests/browser/test_dom_clobbered_properties.py` covers it.

Patchright evaluates the DOM build in an isolated world, where a handler assigned
by a page script is not readable through `element.onclick`. Regressions for those
handler properties in the page world (the Playwright backend) evaluate
`DOM_TREE_JS` with `isolated_context=False`, as the clobbering tests do.

Only an editing host gets the implicit `contenteditable` textbox role. Carry the
host flag from the DOM script into both role classification and duplicate detection;
editable descendants with their own click handlers must retain their click actions.

Off-screen fixed text is unreachable only when its panel is fixed to the viewport.
In Chromium, a fixed element's non-null `offsetParent` identifies a containing block
(for example, a transformed ancestor) that can scroll into view. Walk through shadow
hosts when checking panels, following `assignedSlot` before light-DOM parents;
`parentElement` alone stops inside web components and bypasses slotted panels.
Start direct slotted text at its assigned slot too. A viewport-fixed portal remains
an independent boundary even with an empty box: check its text's reachable bounds
after inner scrolling rather than using an outer drawer's position.
Only expand those bounds for scroll boxes that move the text's positioned ancestor;
absolute or fixed text can escape a static scroll box through its containing block.
Boxless wrappers (`display: contents`) do not establish a positioned owner, even
when their computed `position` is absolute or fixed.
`tests/browser/test_dom_hidden_content.py` covers both cases.

CDP listener hints must retain the inspected elements' identities through main-world
handles. DOM marker attributes are copied by `cloneNode`, while event listeners are
not, so an attribute bridge can incorrectly offer a clone as a clickable header.
The clone regression injects its marker after listener inspection and asserts that
both inspected headers were cloned; an observer alone does not exercise this race.

Wrapper deduplication is covered by `tests/browser/test_dom_clickable_duplicates.py`.
The payload's `clickHandler` only captures DOM handler attributes/properties, not
`addEventListener` listeners; its absence cannot prove a real control has no independent action.

Listbox button selection values read rendered text, including assigned slots and slot fallback,
without following descendant accessible names or ARIA references. Each read stops after 1,024
descendant nodes or 4,096 raw UTF-16 code units (whitespace counts), before text transformation.
The owner authorized this fixed cutoff and partial change detection beyond it. The UTF-16 FNV-1a
digest covers the whitespace-normalized text read; the display retains at most 200 characters.
Within budget the digest covers the entire selection. Budget exhaustion also sets valueTruncated,
even if fewer than 200 normalized characters were read. Traverse assigned slots without native
recursive flattening so nested slot traversal shares the same node budget.

Scroll clipping follows positioned ancestors too: normal-flow controls in an escaping popup escape
with it. Fixed popups with a transformed containing block can still be clipped by that block;
`tests/browser/test_dom_offscreen_controls.py` checks both against Chromium hit testing and clicks.
Cache the escaped clippers from one composed-ancestor walk per element. Rewalking
the chain for every scroll box makes observation cubic when sibling controls and
scroll depth grow together; the browser regression counts ancestor reads instead of timing it.

Off-screen controls use the scroll box's scaled inner bounds, and ancestor walks
follow assigned slots before light-DOM parents and cross shadow roots to their hosts.
A transformed scroll box can hit-test a control
behind its border as the top element, so hit-testing alone cannot establish that
it is in view. `tests/browser/test_dom_offscreen_controls.py` covers these cases.

Editor hit testing and uncovered-area probes share the editor box clipped to the
viewport and overflow ancestors, including ancestors outside its shadow root. Keep
`tests/browser/test_dom_contenteditable.py` and `test_dom_covered_controls.py` passing
together: probing the original editor box loses editors cut by a scroll panel or the fold.

Editing hosts use the center of their visible portion for both hit testing and off-screen
classification. Intersect only axes that clip, using the scaled inner bounds across shadow
hosts, and respect positioned popup escapes; a full-box center can be outside while the
editor still accepts a fill. `tests/browser/test_dom_contenteditable.py` covers this integration.

## Public API

- Don't remove or rename public methods without a deprecation first: keep the
  old name working and emit a `DeprecationWarning` (see `generate_cookies` in
  `notte_sdk/utils.py`).
- API models follow `docs/backward-compatibility.md`.
- If an SDK change needs server-side support that doesn't exist yet, ask
  before changing course. Don't drop or weaken the requirement on your own.

## Locating elements in shadow roots

Playwright's CSS engine enters open shadow roots, its XPath engine does not (not
even after `>>`). The XPath of an element in a shadow root restarts there, so the
observed CSS path is what finds it: `dom/builder.py` builds it on from the host's
(`html > body > my-form > my-field:nth-of-type(2) > input`), as Playwright's `>`
goes from a host to the top elements of its shadow root.

## HTTP transport

The SDK sends HTTP with httpx. Only `_transport.py`, `_retry.py`, `errors.py` and
`endpoints/base.py` in `notte_sdk` import `httpx`, `httpcore` or `requests` (kept for
the exception classes `errors.py` extends). Other SDK code goes through `BaseClient`
and the `_transport` helpers; a test fails on any other import. Offline tests answer
requests with `fake()` from `tests/sdk/test_generated_endpoints.py`, an
`httpx.MockTransport`; don't patch `requests`.

`AsyncNotteClient` uses the async twins in the same modules (`AsyncBaseClient`,
`asend_with_retries`, `astream`, ...). The sync and async I/O are written side by side;
every decision (retry policy, error translation, handshake recovery, encoding, response
checks) lives in one helper both call, so change it there, not in one twin. Async tests use
`afake()` from `tests/sdk/test_async_resources.py`; transport changes need a scenario in
`tests/sdk/test_async_transport.py`, which runs it through both clients and compares.
The stateful layer follows the same rule: an operation that polls or retries over several
requests is one generator in the style of `notte_sdk/_flow.py`, run by `run` (sync) and `arun`
(async), so its decisions are not written twice.

Async code never reads or writes local files on the event loop: use `asyncio.to_thread`
(httpx reads multipart files synchronously, so `AsyncBaseClient._request_upload` reads them
in a thread first). `tests/sdk/test_async_functions_files.py` checks this for functions and files.

## Generated docs

After changing `packages/notte-sdk/src/`, run `make docs-sdk` (the
`docs-sdk-generate` pre-commit hook runs the same target) and commit the
generated files. `make docs-check` fails if they are out of date.
Manual SDK pages repeat constructor parameter fields; keep their type strings
in sync with the generated `__init__.mdx` pages. Docs tests compare both.

## OpenAPI refresh

Every operation in `openapi/openapi.json` needs an entry in
`openapi/resources.json`: a resource method, or `exclude` with a reason. Both
SDK generators also reject entries for operations the spec no longer has, so
add or remove entries in the same change as the spec. The scheduled
`openapi-bump.yml` refresh opens a draft PR and fails when generation or the
contract check fails. Fix it on `chore/bump-openapi`. Scheduled runs leave
that PR alone once it has manual commits.

## Sync facades

Synchronous wrappers over async operations use `notte_core._sync.run_sync`, which
keeps one event loop alive on a background thread. Do not use `asyncio.run` in
these wrappers or patch asyncio with `nest_asyncio`: browser objects belong to
the loop that started them, and callers may already have a running loop.
Local sessions must use one loop from start through stop; mixing sync and async
methods while the browser is active raises `RuntimeError`.
Async compatibility wrappers over synchronous SDK requests use
`notte_sdk._transport.athread`, which settles the worker before propagating
cancellation and preserves its return value. Deletes use `athread_finally`.

The development interpreter is Python 3.15. CI runs the full offline suite on
3.15 and `make test-compat` on 3.11 (syntax/import checks, SDK/core units and a
browser lifecycle smoke test). Keep `requires-python >=3.11` and basedpyright's
`pythonVersion = "3.11"`
so new code remains usable on the supported floor. Use uv 0.13.5 or newer for
the revision-5 lockfile. SDK model generation requires datamodel-code-generator
0.86.0, and reference docs require sphinx-mintlify 0.1.2 or newer for 3.14+ types.
Docs CI syncs the workspace before installing job-only dependencies, then uses
`uv run --no-sync`; a later sync can remove those dependencies or replace an
environment built with a Python version that differs from `.python-version`.
