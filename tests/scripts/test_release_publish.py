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
