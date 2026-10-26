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

- Never add `xfail`, `skip` or an ignore to make a failing test pass. Fix the
  cause, or stop and explain why it fails.
- CI's live LLM calls (`staging-and-live`) go through OpenRouter: the
  `OPENROUTER_API_KEY` secret as `NOTTE_LLM_API_KEY` with `google/...` model
  IDs. Don't point them at a provider's direct API key; the shared direct
  Gemini key hits rate limits. Only `llm-provider-matrix` tests direct routes.
- `make test` is the offline gate. `make test-live` runs tests marked
  `staging` or `live` and needs `NOTTE_API_KEY`; set `NOTTE_API_URL` to point
  the SDK at a different API.
- Native integration examples (`examples/*`, run by
  `scripts/ci_integration_examples.py`) install the local `node-sdk` with
  `npm install --no-save`. Don't add `--package-lock=false`: it ignores the
  example's lockfile, so a new upstream release can break CI.

## Public API

- Don't remove or rename public methods without a deprecation first: keep the
  old name working and emit a `DeprecationWarning` (see `generate_cookies` in
  `notte_sdk/utils.py`).
- API models follow `docs/backward-compatibility.md`.
- If an SDK change needs server-side support that doesn't exist yet, ask
  before changing course. Don't drop or weaken the requirement on your own.

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

## OpenAPI refresh

Every operation in `openapi/openapi.json` needs an entry in
`openapi/resources.json`: a resource method, or `exclude` with a reason. Both
SDK generators also reject entries for operations the spec no longer has, so
add or remove entries in the same change as the spec. The scheduled
`openapi-bump.yml` refresh opens a draft PR and fails when generation or the
contract check fails. Fix it on `chore/bump-openapi`. Scheduled runs leave
that PR alone once it has manual commits.
