# Paired SDK examples

`docs/src/testers` is the source of truth. Add executable `.py` and `.ts` files
with the same relative name. Use `# @sniptest` in Python and `// @sniptest` in
TypeScript. Each file can have its own `filename`, `show`, and highlight ranges.
`make sniptest` generates one MDX `<CodeGroup>` from each pair. Do not edit the
generated snippets. Existing Python-only snippets retain their current output.

Phase 1 starts with client authentication, session cleanup, function invocation,
and optional run creation/retrieval. The remaining examples are listed explicitly
in `parity.json`. This migration backlog cannot grow relative to the PR base;
remove each entry when adding its TypeScript counterpart. New examples require
both languages. Truly Python-only examples may be listed under `python_only`
with a reviewed, specific reason (for example, a Python function-runtime handler).
Missing counterparts, orphan `.ts` files and stale exceptions fail CI.

## Local validation

From the repository root:

```bash
npm ci --prefix node-sdk
npm run build --prefix node-sdk
npm run typecheck --prefix node-sdk
node-sdk/node_modules/.bin/tsc -p docs/src/sniptest/tsconfig.json
python -m unittest discover -s docs/src/sniptest -p 'test_*.py'
python docs/src/sniptest/parity.py --base-ref origin/main
python docs/src/sniptest/generate.py --check
```

TypeScript examples compile against the built local package's public declarations.
Live tests import that same build. Python examples use the local workspace SDK.
The test runner discovers every `.ts` pair and executes both files unchanged;
when adding examples needing other resources, extend the owned fixtures first.
Do not add examples that depend on somebody's existing resource IDs.

```bash
uv sync --locked --package notte-sdk --no-dev
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

Pull requests run credential-free checks. Live execution runs on main pushes or
a manual dispatch on main, never with secrets exposed to pull-request code.
The existing Python docs suite still checks paired examples' syntax and types;
their live execution belongs to the isolated paired suite.

Full SDK-reference MDX generation is a separate phase 2 change.
