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
