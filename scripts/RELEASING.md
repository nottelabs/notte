# Python release versions

The root package, every Python workspace package, and all internal dependency
pins share one version. After `v1.9.0`, development uses `1.9.1.dev0`.

Push `v1.9.1` to release that development version. `build.sh` validates all
package versions and internal pins before changing files or building anything.
The tag must match the workspace version after removing the optional tag `v`
and workspace `.dev`/`.dev0` suffix. Other prerelease forms are rejected.
The build writes the stable version into all package manifests and internal
pins. An already-stable matching workspace is also accepted.

`make release <version>` builds locally and restores the original manifests and
lockfile on success or failure, preserving pre-existing edits and the build exit
status. The CI workflow uses `build.sh` directly to retain stable manifests.

Tag-triggered Node releases validate the same Python workspace version before
publishing. The existing manual Node recovery release remains independent.

After Python publishing and its installation check succeed, the release workflow
opens a PR against the default branch for the next patch development version,
including internal pins and the refreshed `uv.lock`. It uses the existing
`SUBMODULE_BUMP_PAT` secret so PR checks run. The PR is left open for review;
merge it before preparing the next patch release. For a minor or major release,
update all workspace versions and internal pins to that release's development
version and run `uv lock` before tagging.

Rerunning a release does not create a duplicate bump PR. If the default branch
already has a newer version, the workflow skips the bump. It refuses to advance
a branch that is still behind the released version.

The initial adoption of this process advances the old `1.4.4.dev` workspace to
`1.9.1.dev0`, following the latest published release, `v1.9.0`.

These versions identify SDK release cycles. Backend deployments still need to
update their pinned OSS revision to pick up a new version.
