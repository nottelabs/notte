# Selector repair with GitHub Actions

Repair a JSON selector map using a live Notte browser. Each entry declares an
old CSS selector, expected accessible role (`link` or `button`), and exact name.
The Python and TypeScript recipes derive a replacement from the target's actual
`id` or an HTTP(S) `href` without query or fragment. They require one semantic
target and one matching replacement, and refuse cross-origin redirects.

This is deterministic selector-map repair. It does not generate or execute
application code or use a model. Ambiguous, missing or unstable targets require
manual review. Every owned browser closes after success, refusal or cancellation.

On Linux or macOS, use Python 3.11+ or Node.js 24.8+ and a [Notte API key](https://console.notte.cc/apikeys).
Inside this directory run `uv sync --locked` or `npm ci`, set `NOTTE_API_KEY`, then
run `uv run --locked python repair.py` or `npm start`. Edit `selectors.json` for
your page and semantic targets. The recipe writes `proposal.json` without changing
the source map. `NOTTE_API_URL` optionally selects the endpoint matching your key.

## Manual GitHub Actions

Keep this project at `examples/github-actions` in your repository and copy
[selector-repair.yml](../../.github/workflows/selector-repair.yml) into
`.github/workflows`. Add `NOTTE_API_KEY` to your repository's Actions secrets.
Run **Review browser selector repairs** from the Actions tab on `main`. Choose
Python or TypeScript; the default API endpoint is `https://api.notte.cc`.

The default run uploads a proposal artifact for review. Set `create_pr` only when
you want a draft PR. Only that job receives `contents: write` and
`pull-requests: write`; the repository must allow Actions to create PRs.
Publication verifies the producing job's artifact digest, original file hash,
unchanged main commit, fixed map path, and existing repair-branch changes before
using the official GitHub REST API. It changes only known `selector` fields.
Retries reuse the repair branch and draft PR. Nothing merges automatically.

PRs created with `GITHUB_TOKEN` normally do not trigger other workflows. Run
your usual required checks before merging; see GitHub's
[workflow-trigger rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow).

## Validation

Run `uv run --locked python -m unittest test_publish test_cli_signals -v` without credentials for
native GitHub and session-lifecycle HTTP fixtures, including retries, stale/tampered artifacts,
unrelated branches, HTTP 401 and redirects. No remote repository is modified.
With `NOTTE_API_KEY`, run `uv run --locked python -m unittest test_live -v` and
`NOTTE_EXAMPLE_PYTHON=.venv/bin/python npm test` for real DOM and CLI signal tests.
All owned browser IDs receive independent API closure checks.

Creating a hosted GitHub PR with this workflow has not been tested. REST fixture
coverage does not constitute a remote PR-write test.
