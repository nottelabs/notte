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

## Public API

- Don't remove or rename public methods without a deprecation first: keep the
  old name working and emit a `DeprecationWarning` (see `generate_cookies` in
  `notte_sdk/utils.py`).
- API models follow `docs/backward-compatibility.md`.
- If an SDK change needs server-side support that doesn't exist yet, ask
  before changing course. Don't drop or weaken the requirement on your own.

## Generated docs

After changing `packages/notte-sdk/src/`, run `make docs-sdk` (the
`docs-sdk-generate` pre-commit hook runs the same target) and commit the
generated files. `make docs-check` fails if they are out of date.
