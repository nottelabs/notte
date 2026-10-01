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

1. Merge the previous release's automatic development-version PR. Check that
   the Python workspace version matches the intended release by running
   `python3 scripts/release_version.py validate vX.Y.Z` on `main`.
   If the previous workflow failed before opening that PR, run
   `python3 scripts/release_version.py next vPREVIOUS_VERSION` and `uv lock`,
   then commit the changes, open the version PR, and merge it into `main`
   before cutting the next release.
2. Open [Releases](https://github.com/nottelabs/notte/releases) and draft a new
   release with a new tag `vX.Y.Z` targeting `main`. Generate the release notes
   and publish the release.
3. Pushing the tag runs two workflows:
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
