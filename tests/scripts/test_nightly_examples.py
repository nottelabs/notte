"""Keep nightly discovery, staging execution, and production smoke coverage distinct."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts import ci_integration_examples, ci_scope

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("event", ["schedule", "workflow_dispatch"])
def test_nightly_uses_the_complete_registered_runner(event: str, monkeypatch: pytest.MonkeyPatch) -> None:
    nightly = yaml.safe_load((ROOT / ".github/workflows/nightly-examples.yml").read_text())
    registered = nightly["jobs"]["registered-examples"]
    assert registered["uses"] == "./.github/workflows/paired-sdk-examples.yml"
    assert registered["secrets"] == "inherit"  # pragma: allowlist secret
    assert "scope" not in registered.get("with", {})

    # The reusable workflow owns selection and sharding, including newly registered projects.
    scope = ci_scope.select(event, "", "")
    monkeypatch.setenv("INTEGRATION_EXAMPLES", json.dumps(scope["integration_examples"]))
    discovered = [name for shard in scope["paired_shards"] for name, _ in ci_integration_examples.projects(shard)]
    registry: dict[str, str] = json.loads(ci_integration_examples.REGISTRY.read_text())
    assert sorted(discovered) == sorted(registry)
    assert scope["paired_static"] is True
    assert scope["paired_live"] is True


def test_nightly_keeps_registered_and_legacy_execution_on_staging() -> None:
    nightly = yaml.safe_load((ROOT / ".github/workflows/nightly-examples.yml").read_text())
    legacy = nightly["jobs"]["example-tests"]
    paired = yaml.safe_load((ROOT / ".github/workflows/paired-sdk-examples.yml").read_text())
    assert legacy["env"]["NOTTE_API_URL"] == paired["jobs"]["live"]["env"]["NOTTE_API_URL"]
    assert legacy["env"]["NOTTE_API_URL"] == "https://us-staging.notte.cc"
    assert legacy["needs"] == "registered-examples"
    assert "always()" in legacy["if"]
    assert "github.ref == 'refs/heads/main'" in legacy["if"]
    steps = {step.get("name"): step for step in legacy["steps"]}
    execute = steps["Run legacy and README example tests"]
    assert "tests/run_examples.sh" in execute["run"]
    assert execute["env"]["NOTTE_API_KEY"] == "${{ secrets.NOTTE_API_KEY_CI_EXAMPLES || secrets.NOTTE_API_KEY }}"
    assert steps["Cleanup vaults created by this run"]["run"] == "uv run python scripts/cleanup_ci_vaults.py"
    assert not any(step.get("continue-on-error") for step in legacy["steps"])


@pytest.mark.parametrize("registered_result,legacy_result", [("failure", "success"), ("success", "failure")])
def test_nightly_notification_reports_either_suite_failure(
    tmp_path: Path, registered_result: str, legacy_result: str
) -> None:
    nightly = yaml.safe_load((ROOT / ".github/workflows/nightly-examples.yml").read_text())
    step = next(
        step for step in nightly["jobs"]["example-tests"]["steps"] if step.get("name") == "Build Slack notification"
    )
    assert step["env"]["REGISTERED_RESULT"] == "${{ needs.registered-examples.result }}"
    assert step["env"]["LEGACY_RESULT"] == "${{ job.status }}"
    (tmp_path / "pytest_summary.log").write_text("original pytest failure\n")
    subprocess.run(
        ["bash", "-e", "-c", step["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            "RUN_TIMESTAMP": "1234",
            "RUN_URL": "https://example.test/run",
            "REGISTERED_RESULT": registered_result,
            "LEGACY_RESULT": legacy_result,
        },
        check=True,
    )
    payload = json.loads((tmp_path / "slack-payload.json").read_text())
    assert f"Registered integrations (staging): {registered_result}" in payload["text"]
    assert f"Legacy and README examples (staging): {legacy_result}" in payload["text"]
    assert "original pytest failure" in payload["text"]


def test_production_smoke_keeps_its_separate_published_sdk_environment() -> None:
    release = yaml.safe_load((ROOT / ".github/workflows/nightly-test-release.yml").read_text())
    step = next(step for step in release["jobs"]["example-tests"]["steps"] if step.get("name") == "Run test release")
    assert step["run"] == "bash scripts/test_release.sh"
    assert step["env"] == {"NOTTE_RELEASE_TEST_API_KEY": "${{ secrets.NOTTE_RELEASE_TEST_API_KEY }}"}
    script = (ROOT / "scripts/test_release.sh").read_text()
    assert "uv venv --python 3.11" in script
    assert "uv pip install --upgrade notte-sdk" in script
    assert "NOTTE_API_URL" not in script
    assert "<!-- release-test -->" in script
