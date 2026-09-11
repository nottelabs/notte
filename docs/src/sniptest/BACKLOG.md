# Paired example follow-up

This batch adds 18 executable same-name pairs, bringing paired live coverage from
6 to 24 cases (48 script executions). It does not finish the whole migration.
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
