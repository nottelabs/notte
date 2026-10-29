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

Each PR push runs the selected offline checks. Selected staging and model tests
are deferred until a maintainer explicitly authorizes that head's **CI** run and
chooses **Re-run all jobs**. The run summary prints the exact two commands:

```sh
gh api --method POST repos/nottelabs/notte/statuses/HEAD_SHA -f state=success -f context=ci/live-validation/RUN_ID -f target_url=https://github.com/nottelabs/notte/actions/runs/RUN_ID
gh run rerun RUN_ID --repo nottelabs/notte
```

Replace `HEAD_SHA` and `RUN_ID` with that run's commit and ID. The status must be
created by the same human GitHub account that starts the rerun; creating a status
requires repository write permission. The workflow only reads statuses and
rejects workflow-bot authorization. A rerun or a label alone cannot authorize
live work, even when the original suite-selection job failed.

Until then the required `tests` gate reports that live validation is needed,
even when offline checks pass. This is an explicit merge requirement. Re-running
only the gate or only failed jobs cannot create authorization. A new push starts
a new offline run and requires authorization for its new head and run ID.
PRs whose selected scope needs no live tests can pass on their first run.

All selected checks must pass on the current head before merging. Queued live
jobs check the live PR head before dependency installation; obsolete jobs fail
without starting tests. Already-running tests finish and perform their cleanup.
Superseded offline jobs are cancelled independently, without cancelling live jobs.
Native preparation runs in up to six parallel shards, independently of documentation
checks and the live jobs, and remains part of the required result.

Fork PRs receive no secrets. Their live coverage requires a reviewed branch in
this repository. Main pushes and scheduled/manual coverage retain live testing.

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
   workflow on `main` with the version `X.Y.Z`. It checks that the version is a
   stable `X.Y.Z` matching the Python workspace, that no `vX.Y.Z` tag or
   release exists yet, and that production serves the wire models the SDK uses
   (`make openapi-check-prod`). If production fails the check, wait for the
   backend deploy and run it again. When every check passes, it creates a draft
   release `vX.Y.Z` targeting the checked `main` commit, with generated notes.
3. Open the draft on [Releases](https://github.com/nottelabs/notte/releases),
   edit the notes and publish it. Publishing creates the tag. A tag ruleset
   only accepts `vX.Y.Z` names for `v*` tags.
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
