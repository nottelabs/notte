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

The original executable pairs cover client authentication, session cleanup,
function invocation, and optional run creation/retrieval. The extracted API-key
and CDP screenshot quickstarts also execute as paired live tests. The remaining examples are listed explicitly
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

Extraction does not complete translation: there are 488 Python sources and 47
TypeScript sources, including 34 same-name pairs. 454 Python sources still lack a
same-name TypeScript counterpart; some describe Python-only integrations or
function-runtime code. Review these individually before classifying exceptions.
All 86 previously manual snippet files now use the catalog.

## Local validation

From the repository root:

```bash
npm ci --prefix node-sdk
npm run build --prefix node-sdk
npm run typecheck --prefix node-sdk
node docs/src/sniptest/check_typescript.mjs
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

The live suite deploys an isolated echo function, supplies its ID through
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
