"""Selected live coverage runs on every PR push, and obsolete PR heads never satisfy merge validation."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts import ci_integration_examples as runner
from scripts import ci_scope
from scripts.ci_scope import ALL, GROUPS, select
from scripts.ci_validation import Need, Scope, assess
from tests.scripts.test_ci_staging_scope import workflow

ROOT = Path(__file__).resolve().parents[2]


def selected() -> Scope:
    return {**{flag: True for flag in ALL}, "file_checks": True, "integration_examples": ["openai-agents"]}


def results(scope: Scope) -> dict[str, Need]:
    return {
        "changes": {"result": "success", "outputs": {"scope": json.dumps(scope)}},
        **{family: {"result": "success", "outputs": {}} for family in GROUPS},
    }


def test_pr_suites_receive_the_selected_scope_without_approval() -> None:
    config = workflow("ci.yml")
    changes = config["jobs"]["changes"]
    assert changes["outputs"]["scope"] == "${{ steps.scope.outputs.scope }}"
    assert "statuses" not in changes["permissions"]
    assert "ci_validation plan" not in json.dumps(config)
    assert "live_authorized" not in json.dumps(config)
    assert "live_authorized" not in json.dumps(workflow("test-cicd.yml"))


def test_first_push_with_every_suite_passing_can_merge() -> None:
    message, ready = assess(results(selected()))
    assert ready, message


def test_offline_only_scope_can_merge_on_first_run() -> None:
    scope: Scope = {**{flag: False for flag in ALL}, "python_unit": True}
    assert assess(results(scope))[1]


@pytest.mark.parametrize("family", sorted(GROUPS))
@pytest.mark.parametrize("conclusion", ["skipped", "failure", "cancelled"])
def test_selected_suites_must_succeed(family: str, conclusion: str) -> None:
    needs = results(selected())
    needs[family]["result"] = conclusion
    message, ready = assess(needs)
    assert not ready
    assert family in message
    del needs[family]
    assert not assess(needs)[1]


def test_missing_or_invalid_selection_fails_closed() -> None:
    needs = results(selected())
    needs["changes"]["result"] = "failure"
    assert not assess(needs)[1]
    with pytest.raises(ValueError):
        assess(results({}))


def test_gate_cli_reports_the_suite_results(tmp_path: Path) -> None:
    for family, expected in ((None, 0), ("python", 1)):
        needs = results(selected())
        if family:
            needs[family]["result"] = "failure"
        gate = subprocess.run(
            ["python3", "-m", "scripts.ci_validation", "gate"],
            cwd=ROOT,
            env={**os.environ, "RESULTS": json.dumps(needs), "GITHUB_STEP_SUMMARY": str(tmp_path / "summary")},
            capture_output=True,
            text=True,
        )
        assert gate.returncode == expected, gate.stdout + gate.stderr


@pytest.mark.parametrize(
    "state,base,head,expected",
    [
        ("open", "main", "a" * 40, 0),
        ("open", "main", "b" * 40, 1),
        ("closed", "main", "a" * 40, 1),
        ("open", "other", "a" * 40, 1),
    ],
)
def test_queued_job_uses_live_head_metadata(tmp_path: Path, state: str, base: str, head: str, expected: int) -> None:
    action = yaml.safe_load((ROOT / ".github/actions/current-head/action.yml").read_text())
    step = action["runs"]["steps"][0]
    stub = tmp_path / "gh"
    stub.write_text('#!/bin/sh\nprintf \'%s\' "$PR_METADATA" | jq -r "$4"\n')
    stub.chmod(0o755)
    completed = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "GITHUB_REPOSITORY": "fixture/repo",
            "PR_NUMBER": "12",
            "EXPECTED_HEAD": "a" * 40,
            "PR_METADATA": json.dumps({"state": state, "base": {"ref": base}, "head": {"sha": head}}),
        },
        capture_output=True,
        text=True,
    )
    assert completed.returncode == expected, completed.stdout + completed.stderr


def test_parallel_preparation_covers_the_same_selected_shards_without_live_barrier() -> None:
    jobs = workflow("paired-sdk-examples.yml")["jobs"]
    native = jobs["native-checks"]
    assert native["strategy"]["fail-fast"] is False
    assert native["strategy"]["max-parallel"] == 6
    assert native["strategy"]["matrix"] == {"shard": [f"{index}/6" for index in range(1, 7)]}
    assert 'checks --shard "${{ matrix.shard }}"' in str(native["steps"])
    assert "secrets." not in str(native)
    assert native["needs"] == jobs["checks"]["needs"] == "changes"
    for name in ("live", "agent-models"):
        assert jobs[name]["needs"] == "changes"
    scope = select("workflow_dispatch", "", "")
    assert len(scope["paired_matrix"]) > 1


@pytest.mark.parametrize("count", [1, 36, 2000])
def test_fork_registry_growth_cannot_expand_preparation_jobs_or_lose_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    registry = {f"project-{index}": "root-unittest" for index in range(count)}
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry))
    monkeypatch.setattr(runner, "REGISTRY", path)
    monkeypatch.setattr(ci_scope, "INTEGRATION_EXAMPLES", registry)
    monkeypatch.setenv("INTEGRATION_EXAMPLES", json.dumps(list(registry)))
    # Even a selector output containing 1,000 live matrix entries cannot change
    # the literal offline matrix. Every selected project still runs exactly once.
    scope = select("workflow_dispatch", "", "")
    if count == 2000:
        assert len(scope["paired_matrix"]) == 1000
    native = workflow("paired-sdk-examples.yml")["jobs"]["native-checks"]
    shards = native["strategy"]["matrix"]["shard"]
    assert len(shards) == ci_scope.PAIRED_SLOTS == 6
    assert native["strategy"]["max-parallel"] == len(shards)
    discovered = [name for shard in shards for name, _ in runner.projects(shard)]
    assert sorted(discovered) == sorted(registry)


def test_live_jobs_check_freshness_before_setup_and_never_cancel_running_cleanup() -> None:
    for name, identifiers in {
        "test-cicd.yml": ("staging-and-live", "llm-provider-matrix"),
        "node-sdk-ci.yml": ("integration-tests",),
        "docs-tests-cicd.yml": ("execution",),
        "readme-check.yml": ("live",),
        "paired-sdk-examples.yml": ("live", "agent-models"),
    }.items():
        config = workflow(name)
        assert not config.get("concurrency", {}).get("cancel-in-progress")
        for identifier in identifiers:
            job = config["jobs"][identifier]
            steps = job["steps"]
            guard = next(i for i, step in enumerate(steps) if step.get("uses") == "./.github/actions/current-head")
            assert all("checkout@" in step.get("uses", "") for step in steps[:guard])
            assert not job.get("concurrency", {}).get("cancel-in-progress")
            for step in steps[guard + 1 :]:
                if "cleanup" in step.get("name", "").lower():
                    assert "always()" in step.get("if", "")


def test_reusable_callers_grant_head_read_permission_and_gate_rechecks_head() -> None:
    caller = workflow("ci.yml")["jobs"]
    for family in GROUPS:
        assert caller[family]["permissions"]["pull-requests"] in {"read", "write"}
    assert any(step.get("uses") == "./.github/actions/current-head" for step in caller["tests"]["steps"])
    assert workflow("nightly-examples.yml")["permissions"]["pull-requests"] == "read"


def test_offline_supersession_does_not_cancel_matrix_siblings_or_live_cleanup() -> None:
    for name in ("test-cicd.yml", "node-sdk-ci.yml", "paired-sdk-examples.yml"):
        config = workflow(name)
        assert "concurrency" not in config
        for identifier, job in config["jobs"].items():
            concurrency = job.get("concurrency", {})
            if str(concurrency.get("group", "")).startswith("notte-offline-"):
                assert concurrency["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"
                assert identifier not in {
                    "live",
                    "agent-models",
                    "staging-and-live",
                    "llm-provider-matrix",
                    "integration-tests",
                }
                if "matrix" in job.get("strategy", {}):
                    assert "matrix." in concurrency["group"]
