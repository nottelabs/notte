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
- Same-repository PRs run their selected live suites automatically on every push.
  The owner rejected a per-run maintainer approval (status plus rerun) for live
  coverage; don't reintroduce approval or rerun steps without asking.
  Fork PRs get no secrets; when they select live suites, the `tests` gate stays red.
- Never add `xfail`, `skip` or an ignore to make a failing test pass. Fix the
  cause, or stop and explain why it fails.
- CI's live LLM calls (`staging-and-live`) go through OpenRouter: the
  `OPENROUTER_API_KEY` secret as `NOTTE_LLM_API_KEY` with `google/...` model
  IDs. Don't point them at a provider's direct API key; the shared direct
  Gemini key hits rate limits. Extraction and the provider matrix use only
  OpenRouter credentials; the Vertex matrix leg also routes through OpenRouter.
- OpenRouter can send heartbeat frames while an LLM response is pending. HTTPX read
  timeouts reset per chunk; keep the total per-attempt deadline in `LLMEngine` so a
  pending response cannot run until pytest-timeout terminates an xdist worker.
- Live CI prefers `NOTTE_API_KEY_CI_PY` over the legacy `NOTTE_API_KEY` secret.
  Staging persona 403s naming the `CI/CD` workspace indicate a token/workspace
  mismatch. Lucas must supply the workspace-matched `NOTTE_API_KEY_CI_PY`;
  preserve the runtime checks rather than changing code to bypass those 403s.
- `make test` is the offline gate. `make test-live` runs tests marked
  `staging` or `live` and needs `NOTTE_API_KEY`; set `NOTTE_API_URL` to point
  the SDK at a different API.
- A click that opens a file chooser fails with `FileChooserOpenedError`.
  Local `act()` maps either the raised error or failed execution result to
  BLOCKED because it cannot supply a file; `tests/act/test_local_act.py` covers both modes.
- A test that bounds how long a browser action took (`elapsed < ...`) is marked
  `timing`. The parallel suites leave it out; `make test-timing` runs those
  tests one at a time, in CI on the 3.11 leg. Next to parallel browsers, a
  stalled CPU fails such a bound whatever the code does. A lower bound
  (`elapsed >= ...`) cannot fail that way and needs no mark.
- The compatible-dependency suite uses `pytest -n logical`, like the locked
  offline suite. Running those browser tests serially can exhaust the Python
  job's 20-minute budget after the full unit suite has passed.
- CDP transport tests keep real staging sessions and connections but serve page
  fixtures through Patchright routes, so navigation and screenshot coverage does
  not depend on third-party sites loading.
- README live CI uses the official HTTPS Ubuntu archive in the runner's
  `/etc/apt/apt-mirrors.txt`; the Azure mirror has stalled Chromium dependency
  installation before the examples could run.
- For self-contained Node SDK integration pages, use
  `(await session.page()).setContent(...)`. The hosted `goto` action currently
  normalizes `data:` URLs to HTTPS URLs.
- Benchmark JSON can be left truncated by an interrupted worker. Resume must
  rerun unreadable records, and malformed worker output remains a failed run.
  Final-page read errors must preserve landing/step evidence without accepting
  an incomplete final snapshot as a successful task.
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
  Existing-tab recovery retains requests before click dispatch, but qualifies
  replacement navigations against the notification of actual pointer input
  (or the JS fallback click). Actionability waits can outlast background navigation;
  Native clicks use `no_wait_after=True`: the action timeout bounds input, while
  `PageSettle` waits for navigation even if its response has not committed.
  Starting `Locator.click` is not the input boundary. The page binding reports
  input before a handler closes the tab. Reuse one binding per page, clearing
  action callbacks and input listeners after each action; a new binding per click
  would retain callbacks in the driver's page registry.
  Await input delivery inside the existing action timeout before settlement or
  replacement selection, including closed-target acknowledgements. The JS click
  fallback must await its input notification before invoking the handler.
  Queue navigation attribution alongside input bindings: exposed callbacks run
  as tasks, so immediate request timestamps can invert buffered event order.
  Listener leak checks must prime the complete click path before their baseline:
  the driver's injected utility installs its own persistent hit-target interceptor.
  A new tab's fetch can precede that event too. Retain active context requests
  while watching for tabs, then seed the new page's settle tracker; page listeners
  installed after its first script runs otherwise miss its content request.
  Use Python functions for event handlers: Patchright attaches handler metadata,
  so built-in callables such as `set.add` cannot be registered directly.
  The driver can report a closed target from the click that closes its opener;
  accept that click only when a live replacement appears, and wait for it.
  Measure the post-close replacement wait from the page's close event. The click
  can first wait for actionability or input delivery within its own action budget;
  that work is outside the post-close grace period.
  When activating a tracked late tab, retain earlier tabs and their request trackers
  until selection succeeds. A tab closing during activation must not discard the
  surviving candidates or stop watching when none survive.
  A closing popup can start requests on an already-existing tab. Track those
  tabs before the click so the replacement wait retains their in-flight work.
  A help popup can also close back to an existing opener. Wait for that survivor
  and require a successful driver round trip before accepting a target-closed click;
  cached page state alone does not prove the browser is still usable.
  If another unrelated tab survives too, select the popup's actual live opener
  when no new tab was created, and await that opener's tracked requests. A click
  can instead navigate an existing named tab: prefer a single tracked main-frame
  navigation before the opener, including reloads and navigation before commit.
  A fragment navigation sends no request: its main-frame URL change counts as
  the navigation. A target document replaced before the input drops its listener;
  then the click's return is its input time, as when no report comes within
  `_CLICK_INPUT_REPORT_S` (a page listener can stop `pointerdown` first). A
  click that failed counts only a reported input; the JS fallback reports its
  input from the element's current document before clicking. The click's own
  tab settle seeds a new tab's tracker from the context's requests in flight,
  as `BrowserWindow` does.
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
- Chosen-model scraping integration tests use the self-hosted
  `test-resources-lovat.vercel.app/upload_fixture.html` page, shared with file-storage
  tests. Assert its exact heading: an example.com rate-limit page can be scraped
  successfully while containing the wrong content for the extraction test.
  Python checks install each example's locked published SDK before source validation;
  adopting a new SDK API also requires updating its `pyproject.toml` and `uv.lock`.
  Published SDKs 1.9.7 and 1.10.0 need `NOTTE_ENABLE_NEST_ASYNCIO=false` before import for
  native asyncio on Python 3.15. The source SDK no longer applies that patch.
- `evaluate_js` preserves RegExp results as JSON data (`{"r": {"p": source,
  "f": flags}}`), including complete patterns. Patchright 1.64.1 and Playwright
  1.64.0 compile native regex results into Python objects, so native evaluation is
  no longer the format oracle for regexes. Never compile page-controlled patterns
  during result conversion; test their JSON contract, output budgets, and shared
  containers explicitly.

## DOM build script

Act's inner-scroll discovery must retain an executable selector for each offered
direction. Pass it to the scroll action so execution targets the discovered box,
even when the mouse is over a different scroll box. Use native DOM accessors when
building CSS paths across shadow hosts; form controls can clobber those properties.
`tests/act/test_local_act.py` covers executed up/down scrolls in normal and reversed
lists, both in the document and in open shadow roots.

Act offers ARIA sliders and spinbuttons through `TYPE_TEXT`, using their live values
and one shared numeric-typing instruction. Off-screen and disabled controls retain
pressed, selected and expanded state in the decision text. The local driver omits
`GO_BACK` when CDP history has no earlier page beyond the tab's blank start document.
`tests/act/test_local_act.py` checks these contracts on actual browser pages.
Disabled expanded controls can render `aria_expanded="true"` instead of a bare
`expanded` flag; act reads that rendered attribute without treating false values
or state words inside unrelated attribute values as true state.

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
The editable-body exception applies to direct block children by computed display,
including `-webkit-box` and `flow-root list-item`; inline variants are not hosts.
Without visible block hosts, expose the actual body as the textbox instead of
dropping every editing action. Its inline content is not another editing host,
and independent click handlers must still remain actionable.

An image-map `<area>` has `display: none` and no box. The DOM script's
`getBoundingClientRect`/`getClientRects` helpers give it the bounds of its shape on
the visible `<img usemap>` of its `<map>` (`areaRect`; the one in view when several
use the map), and `boxOf` gives that image. Its coords are in the CSS pixels of the
image's box, not its natural size, and a transform scales them on screen.
`isTopElement` hit-tests a grid of points of that box, because a polygon or a
`default` area need not be hit at the center. Image maps are page content: read
the images once per build, and never spread `coords` into a call.
Playwright never finds an `<area>` visible, so a click action uses the element's own
`click()`, which follows its `href`.

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

Off-screen controls use the scroll box's scaled inner bounds on both scrollable axes, and ancestor walks
follow assigned slots before light-DOM parents and cross shadow roots to their hosts.
Skip `display: contents` when caching clipping escapes: a boxless positioned wrapper
does not let its normal-flow descendants escape a scroll box.
A transformed scroll box can hit-test a control
behind its border as the top element, so hit-testing alone cannot establish that
it is in view. `tests/browser/test_dom_offscreen_controls.py` covers these cases.

Editor hit testing and uncovered-area probes share the editor box clipped to the
viewport and overflow ancestors, including ancestors outside its shadow root. Keep
`tests/browser/test_dom_contenteditable.py` and `test_dom_covered_controls.py` passing
together: probing the original editor box loses editors cut by a scroll panel or the fold.

Draggable elements can also have real click behavior. Patchright's isolated
evaluation cannot see a page-assigned `.onclick` property, so do not remove
their cursor-based click actions to represent unsupported dragging. Carry the
explicit HTML `draggable` state into act decisions and freshness checks instead;
`tests/act/test_drag_cursor.py` covers click controls and drag capability disclosure.

Editing hosts use the center of their visible portion for both hit testing and off-screen
classification. Intersect only axes that clip, using the scaled inner bounds across shadow
hosts, and respect positioned popup escapes; a full-box center can be outside while the
editor still accepts a fill. `tests/browser/test_dom_contenteditable.py` covers this integration.

## Public API

- Jev route selection does not require the optional LLM field writer. Incomplete
  `NOTTE_LLM_*` settings leave Jev available without a writer; an LLM decider
  still reports invalid endpoint configuration.
- Cloud SDK resources follow their client: sync client resources have sync I/O;
  async client resources have async I/O. Cloud vaults/personas used by a local
  browser session must come from `AsyncNotteClient` on that session's event loop.
- Cloud SDK sessions follow their client: `NotteClient.Session()` uses `with`,
  sync operations, and `session.page`; `AsyncNotteClient.Session()` uses `async with`,
  async operations, and `await session.page`. The sync session has no async context
  manager, `apage`, or `await_for_auth`.

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

That `>` also goes to the host's light children, so a light child and a top
shadow child of the same tag have the same CSS path. `dom/locate.py` then picks,
among the CSS matches, the element the XPath chain of `selectors_through_shadow_dom`
leads to (`js/shadow_chain_index.js` walks it through each `shadowRoot`), even
when there is one match: a match the chain does not reach is rejected. It never
passes a chain that enters a shadow root to Playwright's XPath engine, which would
find the host's light child instead.

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

`docs/src/tests/test_snippets.py` runs mypy on testers only with `DOCS_TEST_TYPE_CHECK=true`, as
the docs `type-check` CI job sets it. Without it, `typecheck_only` testers pass unchecked locally.

The Sphinx build-finished hook corrects `Answers.usage`: sphinx-mintlify currently marks its
`default_factory` field required. Keep the generated reference aligned with the optional model field.

After changing `packages/notte-sdk/src/`, run `make docs-sdk` (the
`docs-sdk-generate` pre-commit hook runs the same target) and commit the
generated files. `make docs-check` fails if they are out of date.
Manual SDK pages repeat constructor parameter fields; keep their type strings
in sync with the generated `__init__.mdx` pages. Docs tests compare both.
The `docs/package.json` override gives `@browserbasehq/stagehand` the docs' own
`zod`. Stagehand pins an exact `zod`; two copies make `check_typescript.mjs`
compare their schema types and run out of memory.

## OpenAPI refresh

`SessionResponse.playwright_url` was added in #1363 before the API rollout.
Until staging publishes it, retain its optional nullable schema during snapshot
refreshes so regeneration preserves the existing Python and Node SDK field.

Every operation in `openapi/openapi.json` needs an entry in
`openapi/resources.json`: a resource method, or `exclude` with a reason. Both
SDK generators also reject entries for operations the spec no longer has, so
add or remove entries in the same change as the spec. The scheduled
`openapi-bump.yml` refresh opens a draft PR and fails when generation or the
contract check fails. Fix it on `chore/bump-openapi`. Scheduled runs leave
that PR alone once it has manual commits.

OpenAPI refresh compares a temporary order-insensitive representation of JSON objects.
When the incoming schema is otherwise unchanged, keep the committed snapshot byte for
byte and still run the generators. Real schema changes retain the API's declared order.
Never sort generator inputs, parameter lists or documentation to suppress drift.
Intentional presentation-order changes are reviewed edits to the committed snapshot.
`scripts/openapi_order.py` is comparison-only; all array positions remain significant.

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

## act benchmark

`scripts/bench_act/` benchmarks `act()` / `choose()` / `check()` and the observe they read, on local
fixture pages and public sites (see its README). `act-bench.yml` runs it on PRs labelled `act-bench` or
`act-bench-all`, changes under `packages/notte-browser/src/notte_browser/js/`,
`packages/notte-browser/src/notte_browser/dom/`, `packages/notte-core/src/notte_core/act/`,
`packages/notte-llm/src/notte_llm/act.py`,
`scripts/bench_act/` or `.github/workflows/act-bench.yml`, and manual dispatch. PRs compare head against the
merge base; a manual run benches the commit it was started on against its merge base with the default branch,
and never checks out another ref (from the default branch, that code could write its caches). For Jev runners (`notte-local`, `notte-local-html`, `probe-local-jev`), fixture tasks and probes
must pass in every head run except for decider transport errors, which use the separate infra-miss threshold;
public tasks and probes fail only on a clear repeat-by-repeat drop against base.
LLM and scripted task/probe outcomes are report-only. A public site that blocks, shows a CAPTCHA, or redirects
outside its registrable domain is a site miss with evidence, never a pass. Decider transport errors are infra
misses (red above 5% of runs, across non-scripted runners). Landing and final-page evidence takes
precedence over a task checker's success flag. Model-backed runners need `OPENROUTER_API_KEY`;
`notte-local-scripted` and `probe-local-scripted` are model-free and need no API key.
The `act-bench-all` label includes extended fixtures with known browser/act failures. These still fail the
report's fixture rules, even when base also fails; do not weaken the rules to make an all-tier run green.
Harness regressions are in `tests/scripts/test_bench_act.py`. Saved runs resume only for identical run inputs,
including probe selection; reports with `_meta/plan-*.json` use only the runs listed in those plans.
Plans also store each job's expected metadata and run identity. Resume requires a complete result;
reporting rejects mismatched or incomplete payloads as missing valid runs. A coordinator timeout or
runner error cannot become a success because a worker wrote JSON or reached the final page.
Fixture destinations must describe the page the task asks to open. The dark-cookie task's Pricing
destination must not use a form-submission acknowledgement: the decider otherwise returns to the
source after correctly refusing cookies and following the Pricing link.
The upload capability task accepts BLOCKED only with a recorded, unchanged profile form, including
the name, selected files, chosen-file label and validation error. Merely staying on the upload URL
does not prove the runner left the form untouched.
Round-3 fixture validators require the submitted action history: Back from wizard review with standard
delivery before the final express choice, and the completed taken-name check before the available
workspace name. Preserve this evidence on navigation. Wizard submission requires the review step;
Enter in a valid delivery field must not bypass it through a hidden submit button.
Retain the standard-delivery review evidence through later Back visits. Executed
Back clicks are recognized in both accessible-text and rendered-HTML label modes.
The benchmark coordinator, registry and task definitions run under CI's system Python, outside either
version's virtualenv. Keep their imports in the standard library; worker-only code runs inside the
selected version's environment. `test_discovery_works_without_installed_packages` checks this boundary.
