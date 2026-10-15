# CI suite selection

Commit checks validate the code and examples affected by a change. Periodic
checks keep exercising the staging API even when SDK code has not changed.
The selector chooses whole suites, not individual test functions. Shared
configuration must select every suite that consumes it, including README
examples that inherit the root pytest configuration. When adding a cross-suite
dependency, add its input to the selector and a regression case to its tests.

Main pushes and pull requests use the same selector in `scripts/ci_scope.py`.
Pushes compare the event's `before` and `after` commits, including every commit
in the push. Pull requests compare their merge base with the head commit.
The entry workflow `ci.yml` runs one small, credential-free selection job, then
calls only the selected workflow families. Its summary lists selected and skipped
suites. Selection uses only Python's standard library and Git, without installing
the SDK or contacting staging. The complete Git diff avoids GitHub's native path
filter limits. Scheduled and manual workflows still select their full scope
locally. Automatic calls reuse the entry job's decisions without checking out
history or running selection tests again.
Lint checks changed files unless lint/Python configuration changes or broad
coverage is selected; those cases check all files against the new rules.
Generic file checks run even when Python suites are skipped. Node-only changes
use standalone pre-commit without installing the Python SDK workspace; Python
files, Python-related hooks and full lint runs retain the workspace environment.
Deletion-only docs changes explicitly run the global link check, since
pre-commit filters deleted files out of changed-file hooks.

| Change | Checks |
| --- | --- |
| Docs prose, pricing, generated reference text, images | Changed-file hooks, offline docs checks, docs assertions |
| Offline llms.txt generator | Lightweight docs and offline generator tests |
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
Both existing four-hour weekday schedules and the nightly workflows are unchanged.
Existing generated reference workflows keep their dedicated path filters.
Live jobs retain fork protections and the shared staging queue. The required
`tests` check always runs, even when expensive suites are skipped, and
waits for all selected workflow families and fails if selection or a selected
family fails or is cancelled. Cancellation stays within the existing Python and
Node workflows; the entry workflow does not cancel other example suites.

Run the selector's offline regression tests with:

```sh
python3 -m unittest discover -s tests/scripts -p test_ci_scope.py
```
