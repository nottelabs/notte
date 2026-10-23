import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[2]


def test_release_workflow_builds_before_uploading_and_publishing() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/pypi-release.yml").read_text())
    steps = workflow["jobs"]["build"]["steps"]
    names = [step.get("name") for step in steps]

    assert (
        names.index("Build Python distributions")
        < names.index("Store the distribution packages")
        < names.index("Publish to PyPI")
    )

    publish = next(step for step in steps if step.get("name") == "Publish to PyPI")
    command = publish["run"]
    assert "uv publish" in command
    assert "--check-url https://pypi.org/simple" in command
    assert "twine" not in command
    assert "--token" not in command
    assert publish["env"] == {"UV_PUBLISH_TOKEN": "${{ secrets.UV_PUBLISH_TOKEN }}"}


def test_manual_release_uses_uv_environment_credentials() -> None:
    build_script = (ROOT / "build.sh").read_text()

    assert "uv publish" in build_script
    assert "--check-url https://pypi.org/simple" in build_script
    assert "twine upload" not in build_script
    assert "--token" not in build_script


def _load_workflow(name: str) -> dict:
    return yaml.safe_load((ROOT / ".github/workflows" / name).read_text())


def _triggers(workflow: dict) -> dict:
    # PyYAML parses the bare `on:` key as the boolean True.
    return workflow.get("on", workflow.get(True))


def test_python_and_node_releases_share_the_same_tag() -> None:
    python = _load_workflow("pypi-release.yml")
    node = _load_workflow("node-sdk-publish.yml")

    assert _triggers(python) == {"push": {"tags": ["v*"]}}
    assert _triggers(node)["push"] == _triggers(python)["push"]
    assert _triggers(node)["workflow_dispatch"]["inputs"]["version"]["required"] is True

    text = (ROOT / ".github/workflows/node-sdk-publish.yml").read_text()
    assert "node-sdk-v" not in text, "node releases must not use a separate tag prefix"
    assert "NODE_SDK_PUBLISH_ENABLED" not in text, "node publishing must not be gated behind a variable"
    assert "release:" not in text, "node releases are triggered by the tag push, like the python release"


def test_node_release_publishes_the_tag_version_with_provenance() -> None:
    workflow = _load_workflow("node-sdk-publish.yml")
    publish_job = workflow["jobs"]["publish"]
    publish_steps = publish_job["steps"]
    publish_names = [step.get("name") for step in publish_steps]
    verify_job = workflow["jobs"]["verify"]
    verify_steps = verify_job["steps"]

    assert publish_job["permissions"]["id-token"] == "write"
    assert publish_job["environment"] == "npm"
    assert publish_job["outputs"]["version"] == "${{ steps.version.outputs.version }}"
    assert workflow["defaults"]["run"]["working-directory"] == "node-sdk"

    setup = next(step for step in publish_steps if str(step.get("uses", "")).startswith("actions/setup-node@"))
    assert "cache" not in setup["with"]
    assert "cache-dependency-path" not in setup["with"]

    version = next(step for step in publish_steps if step.get("name") == "Set release version")
    assert version["env"] == {
        "RELEASE_TAG": "${{ github.event_name == 'workflow_dispatch' && inputs.version || github.ref_name }}"
    }
    assert 'RELEASE_VERSION="${RELEASE_TAG#v}"' in version["run"]
    assert 'npm version "$RELEASE_VERSION" --no-git-tag-version' in version["run"]

    assert (
        publish_names.index("Set release version")
        < publish_names.index("Smoke-test built package exports")
        < publish_names.index("Publish to npm")
    )
    assert publish_names[-1] == "Publish to npm", "no code should run after publishing in the OIDC job"

    publish = next(step for step in publish_steps if step.get("name") == "Publish to npm")
    assert 'npm view "notte-sdk@${RELEASE_VERSION}" version' in publish["run"]
    assert "npm publish --access public --provenance" in publish["run"]
    assert "NODE_AUTH_TOKEN" not in yaml.safe_dump(workflow)
    assert "NPM_TOKEN" not in yaml.safe_dump(workflow)

    assert verify_job["needs"] == "publish"
    assert verify_job["permissions"] == {}
    verify = next(step for step in verify_steps if step.get("name") == "Install the package from npm")
    assert verify["env"] == {"RELEASE_VERSION": "${{ needs.publish.outputs.version }}"}
    assert (
        'npm install --ignore-scripts --prefer-online --no-audit --no-fund "notte-sdk@${RELEASE_VERSION}"'
        in verify["run"]
    )


def test_python_release_install_check_refreshes_the_pypi_index() -> None:
    workflow = _load_workflow("pypi-release.yml")
    steps = workflow["jobs"]["build"]["steps"]
    install = next(step for step in steps if step.get("name") == "Install the package from PyPI")

    # uv caches the simple index (max-age=600) during `uv publish --check-url`,
    # so without --refresh the freshly uploaded version is invisible to the check.
    assert 'uv pip install --refresh "notte==${RELEASE_TAG}"' in install["run"]


def test_node_package_keeps_a_dev_placeholder_version() -> None:
    import json

    package = json.loads((ROOT / "node-sdk/package.json").read_text())
    assert package["name"] == "notte-sdk"
    assert package["version"] == "0.0.0-dev", "the release version is set from the tag in CI"


@pytest.mark.parametrize("build_exit_code", [0, 42])
def test_node_release_dry_run_restores_existing_manifest_changes(tmp_path: Path, build_exit_code: int) -> None:
    sdk = tmp_path / "node-sdk"
    sdk.mkdir()
    for name in ("Makefile", "package.json", "package-lock.json"):
        shutil.copyfile(ROOT / "node-sdk" / name, sdk / name)

    package = sdk / "package.json"
    lock = sdk / "package-lock.json"
    package.write_text(package.read_text() + "\npre-existing package edit\n")
    lock.write_text(lock.read_text() + "\npre-existing lock edit\n")
    original_package = package.read_bytes()
    original_lock = lock.read_bytes()

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_npm = fake_bin / "npm"
    fake_npm.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = version ]; then\n'
        "  printf changed-by-npm-version > package.json\n"
        "  printf changed-by-npm-version > package-lock.json\n"
        "  exit 0\n"
        "fi\n"
        f'if [ "$1" = run ]; then exit {build_exit_code}; fi\n'
        "exit 0\n"
    )
    fake_npm.chmod(0o755)
    fake_node = fake_bin / "node"
    fake_node.write_text("#!/bin/sh\nexit 0\n")
    fake_node.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    result = subprocess.run(
        ["make", "release", "1.9.0"],
        cwd=sdk,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert (result.returncode == 0) is (build_exit_code == 0)
    assert package.read_bytes() == original_package
    assert lock.read_bytes() == original_lock


def test_release_tag_guard_runs_before_node_publish_and_python_build() -> None:
    node = _load_workflow("node-sdk-publish.yml")["jobs"]["publish"]["steps"]
    names = [step.get("name") for step in node]
    guard = next(step for step in node if step.get("name") == "Validate shared release tag")
    assert guard["if"] == "github.event_name == 'push'"
    assert guard["working-directory"] == "."
    assert 'release_version.py validate "$RELEASE_TAG"' in guard["run"]
    assert names.index("Validate shared release tag") < names.index("Publish to npm")
    build = (ROOT / "build.sh").read_text()
    assert build.index('release_version.py release "$version"') < build.index("uv build")
    assert "set -euo pipefail" in build


def test_development_bump_waits_for_successful_publish_and_opens_reviewable_pr() -> None:
    workflow = _load_workflow("pypi-release.yml")
    job = workflow["jobs"]["next-development-version"]
    assert job["needs"] == "build"
    assert job["concurrency"]["cancel-in-progress"] is False
    assert "GH_TOKEN" not in job["env"]
    write_step = next(step for step in job["steps"] if step.get("name") == "Open version bump pull request")
    assert write_step["env"]["GH_TOKEN"] == "${{ secrets.SUBMODULE_BUMP_PAT }}"
    checkout = job["steps"][0]
    assert checkout["with"]["ref"] == "${{ github.event.repository.default_branch }}"
    assert checkout["with"]["persist-credentials"] is False
    assert "token" not in checkout["with"]
    assert "gh auth setup-git" in write_step["run"]
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert 'release_version.py next "$RELEASE_TAG"' in commands
    assert "uv lock" in commands
    assert "gh pr create" in commands
    assert "--state all" in commands
    assert "gh pr merge" not in commands


@pytest.mark.parametrize("scenario", ["new", "existing_branch", "existing_pr", "no_changes"])
def test_bump_pr_creation_and_recovery(tmp_path: Path, scenario: str) -> None:
    workflow = _load_workflow("pypi-release.yml")
    step = next(
        step
        for step in workflow["jobs"]["next-development-version"]["steps"]
        if step.get("name") == "Open version bump pull request"
    )
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.9.2.dev0"\n')
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "commands.log"
    for tool, behavior in {
        "git": """case "$1" in
  diff) [ "$SCENARIO" = no_changes ]; exit $? ;;
  ls-remote) [ "$SCENARIO" = existing_branch ]; exit $? ;;
esac
""",
        "gh": """if [ "$1 $2" = 'pr list' ] && [ "$SCENARIO" = existing_pr ]; then
  echo 'https://github.com/nottelabs/notte/pull/1234'
fi
if [ "$1 $2" = 'pr create' ]; then
  test -s "$RUNNER_TEMP/python-version-pr.md" || exit 1
fi
""",
    }.items():
        script = fake_bin / tool
        script.write_text(f'#!/bin/sh\nprintf "{tool} %s\\n" "$*" >> "$COMMAND_LOG"\n' + behavior + "exit 0\n")
        script.chmod(0o755)
    result = subprocess.run(
        ["bash", "-e", "-c", step["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "COMMAND_LOG": str(log),
            "SCENARIO": scenario,
            "RUNNER_TEMP": str(tmp_path),
            "RELEASE_TAG": "v1.9.1",
            "BASE_BRANCH": "main",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    commands = log.read_text()
    assert ("gh pr create" in commands) == (scenario in ("new", "existing_branch"))
    assert ("git push" in commands) == (scenario == "new")
    if scenario == "new":
        assert "git push origin chore/python-version-after-v1.9.1" in commands
    assert "gh pr merge" not in commands


def _prepare_step(name: str) -> dict:
    steps = _load_workflow("prepare-release.yml")["jobs"]["draft"]["steps"]
    return next(step for step in steps if step.get("name") == name)


def test_prepare_release_checks_everything_before_drafting_the_release() -> None:
    workflow = _load_workflow("prepare-release.yml")
    job = workflow["jobs"]["draft"]
    steps = job["steps"]
    names = [step.get("name") for step in steps]

    assert list(_triggers(workflow)) == ["workflow_dispatch"]
    assert _triggers(workflow)["workflow_dispatch"]["inputs"]["version"]["required"] is True
    assert "github.ref == 'refs/heads/main'" in job["if"]
    assert workflow["permissions"] == {"contents": "read"}
    assert job["permissions"] == {"contents": "write"}
    assert steps[0]["with"]["persist-credentials"] is False

    # A failing check stops the job before the draft: no step may run past a failure.
    assert not any("continue-on-error" in step or "if" in step for step in steps)
    assert (
        names.index("Check the version and the workspace")
        < names.index("Check the release does not exist yet")
        < names.index("Check the wire models against production")
        < names.index("Draft the release")
    )
    assert names[-1] == "Draft the release"
    assert "make openapi-check-prod" in _prepare_step("Check the wire models against production")["run"]

    draft = _prepare_step("Draft the release")["run"]
    assert 'gh release create "$TAG" --draft --target "$GITHUB_SHA"' in draft
    assert "--generate-notes" in draft
    assert "gh release create" not in "\n".join(step.get("run", "") for step in steps[:-1])


@pytest.mark.parametrize(
    ("version", "tag"), [("1.9.1", "v1.9.1"), ("v1.9.1", "v1.9.1"), ("1.9", None), ("1.9.2", None)]
)
def test_prepare_release_accepts_only_the_workspace_version(tmp_path: Path, version: str, tag: str | None) -> None:
    (tmp_path / "scripts").mkdir()
    shutil.copyfile(ROOT / "scripts/release_version.py", tmp_path / "scripts/release_version.py")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "notte"\nversion = "1.9.1.dev0"\n')
    (tmp_path / "packages").mkdir()
    output = tmp_path / "output"
    output.touch()
    result = subprocess.run(
        ["bash", "-c", _prepare_step("Check the version and the workspace")["run"]],
        cwd=tmp_path,
        env={**os.environ, "VERSION": version, "GITHUB_OUTPUT": str(output)},
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) is (tag is not None), result.stderr
    assert output.read_text() == (f"tag={tag}\n" if tag else "")


@pytest.mark.parametrize("scenario", ["new", "tag", "release"])
def test_prepare_release_rejects_an_existing_tag_or_release(tmp_path: Path, scenario: str) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    # Stands in for `gh api ... --jq`, printing what the filter would select.
    gh = fake_bin / "gh"
    gh.write_text(
        """#!/bin/sh
case "$*" in
  *matching-refs/tags/v1.9.1*) [ "$SCENARIO" = tag ] && echo refs/tags/v1.9.1 ;;
  *releases*) [ "$SCENARIO" = release ] && echo https://github.com/nottelabs/notte/releases/tag/untagged-1 ;;
esac
exit 0
"""
    )
    gh.chmod(0o755)
    result = subprocess.run(
        ["bash", "-c", _prepare_step("Check the release does not exist yet")["run"]],
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "SCENARIO": scenario,
            "TAG": "v1.9.1",
            "GITHUB_REPOSITORY": "nottelabs/notte",
        },
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) is (scenario == "new"), result.stdout + result.stderr
    if scenario != "new":
        assert "v1.9.1 already exists" in result.stdout
