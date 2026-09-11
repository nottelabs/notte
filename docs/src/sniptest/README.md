# Paired SDK examples

`docs/src/testers` is the source of truth. Add executable `.py` and `.ts` files
with the same relative name. Use `# @sniptest` in Python and `// @sniptest` in
TypeScript. Each file can have its own `filename`, `show`, and highlight ranges.
`make sniptest` generates one MDX `<CodeGroup>` from each pair. Do not edit the
generated snippets. Existing Python-only snippets retain their current output.

Every file in `docs/src/snippets` must be generated. There is no exemption for
manually maintained CodeGroups, commands, or response samples. `testers/snippets.json`
maps multi-tab snippets to source files and records tab order, labels, and language.
It supports Python, TypeScript, shell, HTTP requests, JSON responses, and text output.
Existing Python tester files are reused rather than duplicated.

Executable pairs cover client authentication, session lifecycle and error cleanup,
timeouts, proxies, viewport configuration, function invocation, streaming logs,
sequential calls, failure responses, and run creation/retrieval. The API-key
and CDP screenshot quickstarts also execute as paired live tests. Remaining examples are listed explicitly
in `parity.json`. This migration backlog cannot grow relative to the PR base;
remove each entry when adding its TypeScript counterpart. New examples require
both languages. Truly Python-only examples may be listed under `python_only`
with a reviewed, specific reason (for example, a Python function-runtime handler).
Missing counterparts, orphan `.ts` files and stale exceptions fail CI for ordinary
examples. Extracted legacy sources have separate, explicit catalog coverage:
`existing_python_test` preserves the prior Python test path; `execution_pending`
identifies scripts needing fixtures/type validation; `live_tested` identifies
catalog examples executed by the paired runner. The legacy execution backlog
cannot grow on subsequent PRs. It is not a Python-only exception or a passing live test.

Translation is incremental: there are 488 Python sources and 65
TypeScript sources, including 52 same-name pairs. 436 Python sources still lack a
same-name TypeScript counterpart; some describe Python-only integrations or
function-runtime code. Review these individually before classifying exceptions.
All 86 previously manual snippet files now use the catalog.
See `docs/src/sniptest/BACKLOG.md` for follow-up batches and SDK gaps that remain separate.

## Local validation

From the repository root:

```bash
npm ci --prefix node-sdk
npm run build --prefix node-sdk
npm run typecheck --prefix node-sdk
node docs/src/sniptest/check_typescript.mjs
python docs/src/sniptest/live.py
python -m unittest discover -s docs/src/sniptest -p 'test_*.py'
python docs/src/sniptest/parity.py --base-ref origin/main
python docs/src/sniptest/generate.py --check
```

Executable TypeScript examples compile against the built local package's public declarations.
Extracted TypeScript scripts and fragments awaiting fixtures receive syntax checks,
not a misleading claim of full type or live validation. Every catalog Python source
is syntax-checked, shell commands pass `bash -n`, and JSON responses are parsed.
Live tests import the local build. Python examples use the local workspace SDK.
The test runner discovers every executable `.ts` pair outside the explicitly recorded
legacy execution backlog and executes both files unchanged;
when adding examples needing other resources, extend the owned fixtures first.
Do not add examples that depend on somebody's existing resource IDs.

`live-examples.json` declares exact expected JSON output for 18 pairs; the six
original cases retain dedicated checks in the runner. Each new executable pair
must have a nonempty behavior contract. CI rejects missing counterparts, pending
Python counterparts, stale contracts, and contract typos. The scripts themselves
print the result, with no test-time source rewriting. The runner compares both
languages against the same expected values and verifies session closure through
the API, including after the intentionally raised automation error. Stream tests
must produce a known function log as well as the final result. Wrong results,
missing output, and successful exits without assertions cannot pass these checks.

```bash
uv sync --locked --package notte-sdk --no-dev
uv pip install playwright==1.62.0
export NOTTE_API_KEY=your_staging_key
export NOTTE_API_URL=https://us-staging.notte.cc
export NOTTE_DOCS_LIVE=1
export NOTTE_DOCS_PYTHON="$PWD/.venv/bin/python"
cd node-sdk
npx vitest run test/docs-snippets.integration.test.ts
```

The live suite deploys an isolated echo function (with an explicit failure mode), supplies its ID through
`NOTTE_FUNCTION_ID`, checks returned values and closed session state, and deletes
only its own function in teardown. Session examples use context-managed cleanup
and a short idle timeout as a fallback. Tests have bounded timeouts. Hard process
termination can prevent teardown; the function may require manual removal.
The CDP examples navigate to the same URL and write PNG screenshots in both
languages. Tests override `NOTTE_SCREENSHOT_PATH` to owned temporary files,
validate their PNG headers, and remove the directory afterward. By default the
examples save `screenshot.png` in the current directory.

All matching pull requests run credential-free checks. Same-repository PRs also
run live execution against staging before merging. Fork PRs skip the credentialed
job. Live execution also runs on main pushes and manual dispatch on main.
Keep the `pull_request` trigger; do not use `pull_request_target` to execute fork code
with repository secrets.
The existing Python docs suite still checks paired examples' syntax and types;
their live execution belongs to the isolated paired suite.

Full SDK-reference MDX generation is a separate phase 2 change.
