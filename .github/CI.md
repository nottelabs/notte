# CI suite selection

Main pushes and pull requests use the same selector in `scripts/ci_scope.py`.
Pushes compare the event's `before` and `after` commits, including every commit
in the push. Pull requests compare their merge base with the head commit.
Each test workflow starts with a small, credential-free selection job. Its
summary lists the selected and skipped suites. Selection uses only Python's
standard library and Git, without installing the SDK or contacting staging.
Lint checks changed files unless lint/Python configuration changes or broad
coverage is selected; those cases check all files against the new rules.
Deletion-only docs changes explicitly run the global link check, since
pre-commit filters deleted files out of changed-file hooks.

| Change | Checks |
| --- | --- |
| Docs prose, pricing, generated reference text, images | Changed-file hooks, offline docs checks, docs assertions |
| README prose surrounding unchanged fenced code | README static checks and changed-file hooks |
| Executable docs, snippet runners, catalogs, or fenced docs code | Relevant offline and live example suites |
| Python unit tests | Python lint and unit suite |
| Python integration tests | Python lint and live suite |
| Python runtime code, including Markdown prompt templates | Python lint, unit and live suites, plus examples that consume those packages |
| SDK authentication, CLI contract tests, CLI pin, Python dependencies | CLI credential contract matrix, plus related suites |
| Node unit tests | Node build, type checks and unit tests |
| Node runtime or integration code | Node static and live checks, plus affected SDK/README examples |
| Node generation inputs or generated sources | Node checks including comparison with staging's generated API |
| Shared fixtures or workflow configuration | Related suites broaden conservatively |
| Selector changes, unknown paths, unavailable comparison | Broad coverage |

Fenced code comparisons retain code, language and fence options; surrounding
prose does not trigger execution. Added and deleted prose pages are handled the
same way. Renames contribute both their old and new paths. Multiple changed
areas combine their selected suites. Missing history or an invalid comparison
selects broad coverage rather than silently skipping tests.

Manual runs retain full coverage. Python's periodic run retains its live-only
scope; Node's periodic run retains its full checks, including staging drift.
Existing generated reference workflows keep their dedicated path filters.
Live jobs retain fork protections and the shared staging queue. The required
Python `tests` check always runs, even when expensive suites are skipped, and
fails if selection or a selected job fails or is cancelled.

Run the selector's offline regression tests with:

```sh
python3 -m unittest discover -s tests/scripts -p test_ci_scope.py
```
