# Paired example follow-up

The first batch added 18 executable same-name pairs. The CDP follow-up adds five
more: event listeners, connection error handling, timeout bounds, JavaScript
evaluation, and the Playwright alternative. Paired live coverage is now 29 cases
(58 script executions). This does not finish the whole migration.
Run `python docs/src/sniptest/parity.py` for current counts. Untranslated examples
remain in `parity.json`; legacy fixture/type gaps remain in `testers/snippets.json`.
Do not remove an exemption until the corresponding scripts and assertions exist.

## Next batches

- Promote the existing scraping TypeScript sources from syntax-only checks to
  typed, paired execution. Use a controlled page and check extracted content,
  schemas, missing values, links, and images against the same expectations.
- Pair agent examples with bounded step limits and owned personas/vaults; check
  actual answers and cleanup. Do not silently provision billable phone numbers.
- Pair cookies, recordings, and remaining Playwright examples with owned temporary
  files and assertions on the resulting artifacts. Never overwrite user files.
- Review external-provider, MCP, Selenium, and Puppeteer examples individually.
  Their extra dependencies and credentials need explicit isolated fixtures.
- Classify Python function-runtime handlers and Python-only integrations with
  specific reasons. Do not translate server-side Python into unsupported Node
  runtime handlers or label ordinary SDK examples Python-only to clear the backlog.

## SDK/API differences to address separately

### Failed Function runs reported as closed (2026-09-12)

The `functions/management/high_failure_rate` pair reproduces a staging API
inconsistency: `run(..., fail=True, raise_on_failure=False, stream=False)` returns
`status="failed"`, but metadata and `list_runs(only_active=False)` for that same
run return `status="closed"`. This was reproduced with both SDKs using owned
Functions; it is not explained by the default active-only list filter.

Keep the live assertion requiring the seeded failed run to appear among failed
runs. The new pair is registered in live CI and is currently expected to fail on
staging; it is not skipped or counted as a live pass. Investigate failure-status
persistence in an API-focused PR, then rerun both languages. No SDK or backend
implementation changes belong in this example batch.

Separately, successful run metadata exposes `result` as a JSON string, unlike the
decoded result returned by execution. The run-status pair decodes it only in its
hidden validation; the displayed example still prints the returned value.

Source inspection during this batch found that Python examples use convenience
APIs not exposed by the current Node `Session` wrapper: attaching an existing
session by ID, a built-in Playwright `page`, automatic `cookie_file` persistence,
and notebook/CDP viewer helpers. Node's `FunctionRunOptions` also lacks the Python
`timeout` option. Assess these in SDK-focused PRs; do not invent these APIs in
TypeScript examples, silently drop the demonstrated behavior, or weaken type checks.

The paired browser examples here connect Playwright using the returned CDP URL.
They preserve the same navigation task in both languages and assert its result.
Legacy `timeout_minutes` examples in this batch now use the actual
`idle_timeout_minutes` option in both SDKs.

The CDP timeout example previously set only `idle_timeout_minutes=20`. Python
validation and the staging API both reject that configuration because the default
maximum duration is 15 minutes. This example now explicitly sets
`max_duration_minutes=20` in both languages, and the live contract checks both
bounds. No SDK behavior was changed.
