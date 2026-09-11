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

1. Open [Releases](https://github.com/nottelabs/notte/releases) and draft a new
   release with a new tag `vX.Y.Z` targeting `main`. Generate the release notes
   and publish the release.
2. Pushing the tag runs two workflows:
   - `pypi-release.yml` builds and publishes the root `notte` package and every
     package under `packages/` to PyPI as `X.Y.Z`, verifies the install from
     PyPI, then triggers the docs deployment.
   - `node-sdk-publish.yml` builds and publishes the `notte-sdk` npm package as
     `X.Y.Z` with provenance, then verifies the install from npm.

Versions on `main` are placeholders (`1.4.4.dev` in the `pyproject.toml` files,
`0.0.0-dev` in `node-sdk/package.json`); CI sets the real version from the tag.
Do not bump versions in pull requests.

If one workflow fails after the other succeeded, re-run the failed workflow from
the Actions tab. PyPI uploads skip files that already exist, and the npm workflow
detects an existing matching version, skips publishing it again, and continues
with installation verification.
