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
    # A failed dependency must not suppress legacy tests on any dispatch ref.
    # A cancelled run must not start another 75-minute job creating live resources.
    assert legacy["if"] == "${{ !cancelled() }}"
    steps = {step.get("name"): step for step in legacy["steps"]}
    execute = steps["Run legacy and README example tests"]
    assert "tests/run_examples.sh" in execute["run"]
    assert execute["env"]["NOTTE_API_KEY"] == "${{ secrets.NOTTE_API_KEY_CI_EXAMPLES || secrets.NOTTE_API_KEY }}"
    assert steps["Cleanup vaults created by this run"]["run"] == "uv run python scripts/cleanup_ci_vaults.py"
    assert steps["Cleanup vaults created by this run"]["if"] == "always()"
    assert not any(step.get("continue-on-error") for step in legacy["steps"])


def test_nightly_reports_outside_execution_gates_on_every_ref() -> None:
    nightly = yaml.safe_load((ROOT / ".github/workflows/nightly-examples.yml").read_text())
    report = nightly["jobs"]["report"]
    assert set(report["needs"]) == {"registered-examples", "example-tests"}
    assert report["if"] == "${{ always() }}"
    assert all(step["if"] == "always()" for step in report["steps"])
    assert "NOTTE_API_KEY" not in str(report)
    triggers = nightly[True]  # PyYAML reads the bare on: key as True.
    assert "legacy/README tests on any ref" in triggers["workflow_dispatch"]["inputs"]["test_filter"]["description"]
    assert "registered live checks on main" in triggers["workflow_dispatch"]["inputs"]["test_filter"]["description"]


@pytest.mark.parametrize("has_summary", [True, False])
def test_nightly_passes_a_bounded_json_summary_to_reporting(tmp_path: Path, has_summary: bool) -> None:
    nightly = yaml.safe_load((ROOT / ".github/workflows/nightly-examples.yml").read_text())
    legacy = nightly["jobs"]["example-tests"]
    capture = next(step for step in legacy["steps"] if step.get("name") == "Capture legacy example summary")
    assert capture["if"] == "always()"
    assert legacy["outputs"]["summary"] == "${{ steps.summary.outputs.summary }}"
    original = '\x1b[31moriginal failure\x1b[0m\n"quotes" and $literal\n' + "x" * 12000
    if has_summary:
        (tmp_path / "pytest_summary.log").write_text(original)
    output = tmp_path / "output"
    subprocess.run(
        ["bash", "-e", "-c", capture["run"]],
        cwd=tmp_path,
        env={**os.environ, "GITHUB_OUTPUT": str(output)},
        check=True,
    )
    lines = output.read_text().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("summary=")
    summary = json.loads(lines[0].removeprefix("summary="))
    if has_summary:
        assert summary == original.replace("\x1b[31m", "").replace("\x1b[0m", "")[:12000]
    else:
        assert "summary unavailable" in summary


@pytest.mark.parametrize("ref", ["refs/heads/main", "refs/heads/fix/example"])
@pytest.mark.parametrize(
    "registered_result,legacy_result,summary",
    [
        ("failure", "success", "original pytest failure\n"),
        ("success", "failure", "original pytest failure\n"),
        ("failure", "failure", None),
        ("cancelled", "skipped", None),
        ("success", "cancelled", None),
    ],
)
def test_nightly_notification_reports_failures_and_cancellation_on_any_ref(
    tmp_path: Path, registered_result: str, legacy_result: str, summary: str | None, ref: str
) -> None:
    nightly = yaml.safe_load((ROOT / ".github/workflows/nightly-examples.yml").read_text())
    step = next(step for step in nightly["jobs"]["report"]["steps"] if step.get("name") == "Build Slack notification")
    assert step["env"]["REGISTERED_RESULT"] == "${{ needs.registered-examples.result }}"
    assert step["env"]["LEGACY_RESULT"] == "${{ needs.example-tests.result }}"
    assert step["env"]["SUMMARY_JSON"] == "${{ needs.example-tests.outputs.summary }}"
    assert step["env"]["REGISTERED_LIVE_ENABLED"] == "${{ github.ref == 'refs/heads/main' }}"
    subprocess.run(
        ["bash", "-e", "-c", step["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            "RUN_TIMESTAMP": "1234",
            "RUN_URL": "https://example.test/run",
            "REGISTERED_RESULT": registered_result,
            "LEGACY_RESULT": legacy_result,
            "SUMMARY_JSON": json.dumps(summary) if summary is not None else "",
            "REGISTERED_LIVE_ENABLED": "true" if ref == "refs/heads/main" else "false",
        },
        check=True,
    )
    payload = json.loads((tmp_path / "slack-payload.json").read_text())
    assert f"Registered integrations: {registered_result}" in payload["text"]
    assert f"Legacy and README examples (staging): {legacy_result}" in payload["text"]
    assert ("main only; not run on this ref" in payload["text"]) is (ref != "refs/heads/main")
    if summary is not None:
        assert summary in payload["text"]
    else:
        assert "summary unavailable" in payload["text"]


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
