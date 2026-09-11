from pathlib import Path

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
    assert _triggers(node) == _triggers(python)

    text = (ROOT / ".github/workflows/node-sdk-publish.yml").read_text()
    assert "node-sdk-v" not in text, "node releases must not use a separate tag prefix"
    assert "NODE_SDK_PUBLISH_ENABLED" not in text, "node publishing must not be gated behind a variable"
    assert "release:" not in text, "node releases are triggered by the tag push, like the python release"


def test_node_release_publishes_the_tag_version_with_provenance() -> None:
    workflow = _load_workflow("node-sdk-publish.yml")
    publish_job = workflow["jobs"]["publish"]
    steps = publish_job["steps"]
    names = [step.get("name") for step in steps]

    assert publish_job["permissions"]["id-token"] == "write"
    assert publish_job["environment"] == "npm"
    assert workflow["defaults"]["run"]["working-directory"] == "node-sdk"

    version = next(step for step in steps if step.get("name") == "Set release version from tag")
    assert version["env"] == {"RELEASE_TAG": "${{ github.ref_name }}"}
    assert 'RELEASE_VERSION="${RELEASE_TAG#v}"' in version["run"]
    assert 'npm version "$RELEASE_VERSION" --no-git-tag-version' in version["run"]

    assert (
        names.index("Set release version from tag")
        < names.index("Smoke-test built package exports")
        < names.index("Publish to npm")
        < names.index("Install the package from npm")
    )

    publish = next(step for step in steps if step.get("name") == "Publish to npm")
    assert publish["run"] == "npm publish --access public --provenance"
    assert "NODE_AUTH_TOKEN" not in yaml.safe_dump(workflow)
    assert "NPM_TOKEN" not in yaml.safe_dump(workflow)

    verify = next(step for step in steps if step.get("name") == "Install the package from npm")
    assert 'npm install --prefer-online --no-audit --no-fund "notte-sdk@${RELEASE_VERSION}"' in verify["run"]


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
