"""Deferred live coverage and obsolete PR heads must never satisfy merge validation."""

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
from scripts.ci_validation import LIVE, Need, Scope, Status, assess, authorized, plan
from tests.scripts.test_ci_staging_scope import workflow

ROOT = Path(__file__).resolve().parents[2]


def selected() -> Scope:
    return {**{flag: True for flag in ALL}, "file_checks": True, "integration_examples": ["openai-agents"]}


def approval() -> Status:
    return {
        "context": "ci/live-validation/123",
        "state": "success",
        "url": "https://api.github.com/repos/fixture/repo/statuses/" + "a" * 40,
        "target_url": "https://github.com/fixture/repo/actions/runs/123",
        "creator": {"login": "maintainer"},
    }


def test_failed_selection_reruns_never_authorize_live_coverage_by_attempt_number() -> None:
    for attempt in (1, 2, 3, 50):
        execution, deferred = plan(selected(), "pull_request", attempt)
        assert deferred
        assert all(execution[flag] is False for flag in LIVE)


@pytest.mark.parametrize(
    "head,run_id,actor",
    [
        ("a" * 40, "123", "maintainer"),
        ("b" * 40, "123", "maintainer"),
        ("a" * 40, "124", "maintainer"),
        ("a" * 40, "123", "someone-else"),
    ],
)
def test_authorization_binds_head_run_and_rerunning_maintainer(head: str, run_id: str, actor: str) -> None:
    assert authorized([approval()], "fixture/repo", head, run_id, actor) is (
        head == "a" * 40 and run_id == "123" and actor == "maintainer"
    )


def test_revocation_and_workflow_bot_statuses_do_not_authorize_live_work() -> None:
    revoked = approval()
    revoked.update(context="CI/LIVE-VALIDATION/123", state="failure")
    assert not authorized([revoked, approval()], "fixture/repo", "a" * 40, "123", "maintainer")
    bot = approval()
    bot["creator"] = {"login": "github-actions[bot]"}
    assert not authorized([bot], "fixture/repo", "a" * 40, "123", "github-actions[bot]")
    assert not authorized([], "fixture/repo", "a" * 40, "123", "maintainer")


@pytest.mark.parametrize("has_authorization", [False, True])
def test_workflow_reads_authorization_for_the_exact_head_before_planning(
    tmp_path: Path, has_authorization: bool
) -> None:
    changes = workflow("ci.yml")["jobs"]["changes"]
    step = next(item for item in changes["steps"] if item.get("id") == "validation")
    assert changes["permissions"]["statuses"] == "read"
    assert step["env"]["TRIGGERING_ACTOR"] == "${{ github.triggering_actor }}"
    assert step["env"]["HEAD_SHA"] == "${{ github.event.pull_request.head.sha || github.sha }}"
    source = tmp_path / "statuses.json"
    source.write_text(json.dumps([[approval()]] if has_authorization else []))
    stub = tmp_path / "gh"
    stub.write_text("""#!/usr/bin/env python3
import os, sys
from pathlib import Path
assert sys.argv[1:] == ["api", "--paginate", "--slurp", "repos/fixture/repo/commits/" + "a" * 40 + "/statuses?per_page=100"]
print(Path(os.environ["STATUS_SOURCE"]).read_text())
""")
    stub.chmod(0o755)
    output = tmp_path / "output"
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "SCOPE": json.dumps(selected()),
            "EVENT_NAME": "pull_request",
            "RUN_ATTEMPT": "2",  # Includes a failed-selection rerun.
            "TRUSTED_LIVE": "true",
            "GITHUB_REPOSITORY": "fixture/repo",
            "GITHUB_RUN_ID": "123",
            "HEAD_SHA": "a" * 40,
            "TRIGGERING_ACTOR": "maintainer",
            "STATUS_SOURCE": str(source),
            "AUTHORIZATION_STATUSES": str(tmp_path / "authorization.json"),
            "GITHUB_OUTPUT": str(output),
            "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    outputs = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert outputs["live_authorized"] == str(has_authorization).lower()
    assert outputs["live_deferred"] == str(not has_authorization).lower()


def results(scope: Scope, attempt: int, live_authorized: bool = False) -> dict[str, Need]:
    execution, deferred = plan(scope, "pull_request", attempt, live_authorized=live_authorized)
    return {
        "changes": {
            "result": "success",
            "outputs": {
                "scope": json.dumps(execution),
                "selected_scope": json.dumps(scope),
                "live_deferred": str(deferred).lower(),
            },
        },
        **{family: {"result": "success", "outputs": {}} for family in GROUPS},
    }


def test_first_push_runs_all_selected_offline_checks_but_cannot_merge() -> None:
    scope = selected()
    execution, deferred = plan(scope, "pull_request", 1)
    assert deferred
    assert scope == selected()
    for flag, value in scope.items():
        assert execution[flag] == (False if flag in LIVE else value)
    message, ready = assess(results(scope, 1))
    assert not ready
    assert "Re-run all jobs" in message


@pytest.mark.parametrize("event", ["push", "schedule", "workflow_dispatch"])
def test_main_and_periodic_coverage_are_not_deferred(event: str) -> None:
    assert plan(selected(), event, 1) == (selected(), False)


def test_deliberate_full_rerun_validates_every_selected_suite() -> None:
    assert plan(selected(), "pull_request", 2, live_authorized=True) == (selected(), False)
    assert assess(results(selected(), 2, live_authorized=True))[1]


def test_rerun_cannot_authorize_fork_secrets_or_claim_fork_live_coverage() -> None:
    for attempt in (1, 2, 3):
        execution, deferred = plan(selected(), "pull_request", attempt, trusted=False, live_authorized=True)
        assert deferred
        assert all(execution[flag] is False for flag in LIVE)


def test_new_push_invalidates_live_authorization_and_gate_only_rerun_cannot_restore_it() -> None:
    assert assess(results(selected(), 2, live_authorized=True))[1]
    new_run = results(selected(), 1)
    # Re-running just the failed gate retains the original changes-job outputs.
    assert not assess(new_run)[1]
    assert not assess(json.loads(json.dumps(new_run)))[1]


def test_offline_only_scope_can_merge_on_first_run() -> None:
    scope: Scope = {**{flag: False for flag in ALL}, "python_unit": True}
    assert plan(scope, "pull_request", 1) == (scope, False)
    assert assess(results(scope, 1))[1]


@pytest.mark.parametrize("family", sorted(GROUPS))
@pytest.mark.parametrize("conclusion", ["skipped", "failure", "cancelled"])
def test_selected_suites_must_succeed(family: str, conclusion: str) -> None:
    needs = results(selected(), 2, live_authorized=True)
    needs[family]["result"] = conclusion
    assert not assess(needs)[1]
    del needs[family]
    assert not assess(needs)[1]


@pytest.mark.parametrize("flag", sorted(LIVE))
def test_removed_live_coverage_cannot_satisfy_gate(flag: str) -> None:
    needs = results(selected(), 2, live_authorized=True)
    execution = json.loads(needs["changes"]["outputs"]["scope"])
    execution[flag] = False
    needs["changes"]["outputs"]["scope"] = json.dumps(execution)
    assert not assess(needs)[1]


def test_missing_example_selection_or_shards_cannot_satisfy_gate() -> None:
    needs = results(selected(), 2, live_authorized=True)
    execution = json.loads(needs["changes"]["outputs"]["scope"])
    execution["integration_examples"] = []
    needs["changes"]["outputs"]["scope"] = json.dumps(execution)
    assert not assess(needs)[1]


def test_offline_failure_is_reported_before_deferred_live_validation() -> None:
    needs = results(selected(), 1)
    needs["python"]["result"] = "failure"
    message, ready = assess(needs)
    assert not ready
    assert "python" in message


@pytest.mark.parametrize("scope,attempt", [({}, 1), (selected(), 0)])
def test_missing_or_invalid_planning_metadata_fails_closed(scope: Scope, attempt: int) -> None:
    with pytest.raises(ValueError):
        plan(scope, "pull_request", attempt)


def test_cli_outputs_survive_the_actual_plan_to_gate_boundary(tmp_path: Path) -> None:
    output = tmp_path / "output"
    summary = tmp_path / "summary"
    authorization = tmp_path / "authorization.json"
    env = {
        **os.environ,
        "SCOPE": json.dumps(selected()),
        "EVENT_NAME": "pull_request",
        "TRUSTED_LIVE": "true",
        "AUTHORIZATION_STATUSES": str(authorization),
        "GITHUB_REPOSITORY": "fixture/repo",
        "GITHUB_RUN_ID": "123",
        "HEAD_SHA": "a" * 40,
        "TRIGGERING_ACTOR": "maintainer",
        "GITHUB_OUTPUT": str(output),
        "GITHUB_STEP_SUMMARY": str(summary),
    }
    for attempt in (1, 2):
        output.write_text("")
        authorization.write_text(json.dumps([[approval()]] if attempt == 2 else []))
        completed = subprocess.run(
            ["python3", "-m", "scripts.ci_validation", "plan"],
            cwd=ROOT,
            env={**env, "RUN_ATTEMPT": str(attempt)},
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        outputs = dict(line.split("=", 1) for line in output.read_text().splitlines())
        needs = results(selected(), attempt, live_authorized=attempt == 2)
        needs["changes"]["outputs"] = {**outputs, "selected_scope": json.dumps(selected())}
        gate = subprocess.run(
            ["python3", "-m", "scripts.ci_validation", "gate"],
            cwd=ROOT,
            env={**env, "RESULTS": json.dumps(needs)},
            capture_output=True,
            text=True,
        )
        assert gate.returncode == (1 if attempt == 1 else 0), gate.stdout + gate.stderr


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
