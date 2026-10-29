# How to Contribute

You can contribute to Notte by submitting a PR or by reporting an issue.

## Submitting a PR

1. Fork the repository
2. Create a new branch
3. Make your changes
4. Submit a PR

Changes to Pydantic models used by the API must follow the
[backward-compatibility guide](backward-compatibility.md), including checks for
both validation and serialization schemas.

## CI validation before merging

Each push to a same-repository PR runs the selected offline and live checks
automatically. No authorization or rerun is needed.

All selected checks must pass on the current head before merging. Queued live
jobs check the live PR head before dependency installation; obsolete jobs fail
without starting tests. Already-running tests finish and perform their cleanup.
Superseded offline jobs are cancelled independently, without cancelling live jobs.
Native preparation runs in up to six parallel shards, independently of documentation
checks and the live jobs, and remains part of the required result.

Fork PRs receive no secrets. Their live coverage requires a reviewed branch in
this repository; until then the `tests` gate stays red when the fork's change
selects live suites. Main pushes and scheduled/manual coverage retain live testing.

## Reporting an Issue

1. Check if the issue already exists
2. If it doesn't, create a new issue
3. Provide a detailed description of the issue
4. Provide a code example if possible

## Installing Notte

Follow the instructions in the [setup docs](../docs/setup.md) file.

## Releasing

The Python packages and the Node SDK are released together, from one tag and at
one version. To cut a release:

1. Merge the previous release's automatic development-version PR.
   If the previous Python release published and passed its installation check,
   but the workflow failed before opening that PR, run
   `python3 scripts/release_version.py next vPREVIOUS_VERSION` and `uv lock`,
   then commit the changes, open the version PR, and merge it into `main`
   before cutting the next release.
2. Run the [Prepare release](https://github.com/nottelabs/notte/actions/workflows/prepare-release.yml)
   workflow on `main` with the version `X.Y.Z` and, optionally, the full SHA of
   the `main` commit to release (empty means the current `main`). It checks
   that the commit is on `main`, that the version is a stable `X.Y.Z` matching
   the Python workspace at that commit, and that `vX.Y.Z` is not published or
   tagged yet. It then creates a draft release `vX.Y.Z` targeting that commit,
   with generated notes. A draft of the same commit is kept with its notes; a
   draft of another commit is replaced.
3. Once production serves the wire models the SDK uses, run
   [Publish release](https://github.com/nottelabs/notte/actions/workflows/publish-release.yml)
   on `main` with the same version and commit. It finds the draft of that
   commit, runs `make openapi-check-prod` and publishes the draft. You can also
   edit the notes and publish the draft from
   [Releases](https://github.com/nottelabs/notte/releases); `pypi-release.yml`
   runs the same production check before uploading. Publishing creates the
   tag. A tag ruleset only accepts `vX.Y.Z` names for `v*` tags.
4. Pushing the tag runs two workflows:
   - `pypi-release.yml` builds and publishes the root `notte` package and every
     package under `packages/` to PyPI as `X.Y.Z`, verifies the install from
     PyPI, then triggers the docs deployment.
   - `node-sdk-publish.yml` builds and publishes the `notte-sdk` npm package as
     `X.Y.Z` with provenance, then verifies the install from npm.

Python versions and internal dependency pins on `main` must match the release
version, optionally with a `.dev` or `.dev0` suffix. For example, `v1.9.4`
accepts `1.9.4.dev0`; CI removes the development suffix when building packages.
The Node SDK keeps `0.0.0-dev` in `node-sdk/package.json`; CI sets its version
from the same tag. After a successful Python release job, CI opens a PR to
advance the Python workspace to the next patch development version. Merge that
PR before cutting the next patch release.

If one workflow fails after the other succeeded, re-run the failed workflow from
the Actions tab. PyPI uploads skip files that already exist, and the npm workflow
detects an existing matching version, skips publishing it again, and continues
with installation verification.
