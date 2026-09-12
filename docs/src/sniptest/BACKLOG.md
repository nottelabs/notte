# Paired example follow-up

The first batch added 18 executable same-name pairs. The CDP follow-up adds five
more: event listeners, connection error handling, timeout bounds, JavaScript
evaluation, and the Playwright alternative. Paired live coverage is now 29 cases
(58 script executions). This does not finish the whole migration.
Run `python docs/src/sniptest/parity.py` for current counts. Untranslated examples
remain in `parity.json`; legacy fixture/type gaps remain in `testers/snippets.json`.
Do not remove an exemption until the corresponding scripts and assertions exist.

## Next batches

The session-artifacts follow-up pairs explicit CDP screenshots, the built-in
Playwright page, automatic cookie-file loading/saving, and both desktop/laptop
viewport examples. Artifact examples execute in separate owned temporary
directories for each language. Their tests verify PNG bytes and persisted
browser cookies; viewport tests verify both configurations and both closures.
Recording examples still need review: several use nonexistent selectors on
example.com or request replay while the session is still active.

The browser/settings batch adds 17 executable pairs (34 script executions):
navigation, reload, keyboard actions, scrolling, explicit waits, built-in proxies,
captcha configuration, stealth configuration, and environment-dependent viewing.
The two scroll examples now use a long page, with downward movement before
scrolling up. The two proxy/stealth observation examples explicitly navigate
before observing because the current SDK rejects `observe(url=...)`.

This leaves 369 entries in `parity.json`, plus 70 legacy catalog scripts awaiting
execution fixtures. There are 65 executable paired cases in total. Captcha
configuration coverage checks session setup and cleanup, not successful solving
of a third-party captcha. External proxies, billable identities, Python function
handlers, and third-party integrations still need individual review; they have
not been hidden behind new exemptions.

Post-stop status can briefly remain active while cleanup persists (reproduced
as active, then closed 500 ms later). Completed-lifecycle contracts use the
existing bounded closure poll and verify its returned response, rather than
requiring an immediate closed snapshot in the displayed examples.

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

The scraping basics batch adds six executable pairs: `quick_scrape`, `quickstart`,
`simple`, `content_filtering`, `link_placeholders`, and `links_and_images`. Four
promote existing legacy TypeScript examples. Their live contracts check real
markdown content from the original public URLs, not just successful process exit.
They also check the actual IANA link placeholder and link inclusion/exclusion.
The example.com page has no images or substantial navigation/sidebar content:
these examples execute the displayed options but do not prove image inclusion
or main-content filtering differences. Controlled-page option-sensitive coverage,
structured extraction, and placeholder-domain examples remain follow-up work.
The function invocation/monitoring batch adds six caller-side pairs: parameterized
invocation, parallel invocation, timeout configuration, polling, run inspection,
and version inspection. Fixtures use an owned echo function and verify returned
values, run identities, and version metadata. Python function-runtime handlers
remain separate work; these examples do not imply a Node deployment runtime.

Node now exposes `FunctionRunOptions.timeoutMs`; the paired timeout lesson converts
Python's seconds to milliseconds. This supersedes the missing-timeout observation
below without changing either SDK.

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
