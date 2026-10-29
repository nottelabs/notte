"""Exercise missing coverage and separate CI failure reporting."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.ci_report import Job, Need, report
from scripts.ci_scope import GROUPS


def needs(scope: dict[str, bool | list[str]]) -> dict[str, Need]:
    return {
        "changes": {"result": "success", "outputs": {"scope": json.dumps(scope)}},
        **{name: {"result": "success", "outputs": {}} for name in GROUPS},
    }


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped"])
def test_selected_suite_cannot_disappear(result: str) -> None:
    results = needs({"node_static": True})
    results["node"]["result"] = result
    assert not report(results, [], True)[1]


def test_fork_withheld_credentials_are_explicit() -> None:
    results = needs({"python_live": True})
    results["python"]["result"] = "skipped"
    summary, accepted = report(results, [], False)
    assert accepted
    assert "credentials withheld" in summary


@pytest.mark.parametrize("conclusion", ["success", "failure", "cancelled", "skipped", None])
def test_every_selected_paired_shard_is_required(conclusion: str | None) -> None:
    results = needs({"paired_live": True, "paired_shards": ["1/2", "2/2"]})
    jobs: list[Job] = [{"name": "paired / live (1/2)", "conclusion": "success"}]
    assert not report(results, jobs, True)[1]
    jobs.append({"name": "paired / live (2/2)", "conclusion": conclusion})
    assert report(results, jobs, True)[1] == (conclusion == "success")


def test_failure_sections_do_not_claim_environment_readiness() -> None:
    jobs: list[Job] = [
        {"name": "python / tests (3.15)", "conclusion": "success"},
        {"name": "node / integration-tests", "conclusion": "failure"},
        {"name": "paired / agent-models (claude-agents)", "conclusion": "success"},
        {"name": "python / llm-provider-matrix", "conclusion": "skipped"},
    ]
    summary, _ = report(needs({"node_live": True}), jobs, True)
    assert "## Code correctness\n\n| Job | Result |\n| --- | --- |\n| python / tests (3.15) | success |\n\n" in summary
    assert (
        "## Staging integrations\n\n| Job | Result |\n| --- | --- |\n| node / integration-tests | failure |\n"
        "| paired / agent-models (claude-agents) | success |\n" in summary
    )
    assert (
        "## Provider behavior\n\n| Job | Result |\n| --- | --- |\n| python / llm-provider-matrix | skipped |" in summary
    )
    assert "not independent availability probes" in summary


def test_scope_failure_is_not_complete_coverage() -> None:
    results = needs({})
    results["changes"]["result"] = "failure"
    assert not report(results, [], True)[1]


def test_successful_family_does_not_hide_a_missing_selected_job() -> None:
    results = needs({"node_static": True})
    jobs: list[Job] = [{"name": "node / tests (22)", "conclusion": "success"}]
    summary, accepted = report(results, jobs, True)
    assert not accepted
    assert "- node / tests (24)" in summary
    jobs.append({"name": "node / tests (24)", "conclusion": "success"})
    assert report(results, jobs, True)[1]


def test_fork_still_requires_selected_offline_jobs() -> None:
    assert not report(needs({"node_static": True}), [], False)[1]


def test_selected_native_example_shards_are_required() -> None:
    results = needs({"paired_static": True, "integration_examples": ["claude-agents"]})
    jobs: list[Job] = [{"name": "paired / checks", "conclusion": "success"}]
    jobs += [{"name": f"paired / native-checks ({shard}/6)", "conclusion": "success"} for shard in range(1, 6)]
    summary, accepted = report(results, jobs, False)
    assert not accepted
    assert "- paired / native-checks (6/6)" in summary
    jobs.append({"name": "paired / native-checks (6/6)", "conclusion": "success"})
    assert report(results, jobs, False)[1]
    assert report(needs({"paired_static": True, "integration_examples": []}), jobs[:1], False)[1]


def test_mixed_fork_suite_reports_withheld_live_coverage_after_offline_success() -> None:
    jobs: list[Job] = [
        {"name": "node / tests (22)", "conclusion": "success"},
        {"name": "node / tests (24)", "conclusion": "success"},
        {"name": "node / integration-tests", "conclusion": "skipped"},
    ]
    summary, accepted = report(needs({"node_static": True, "node_live": True}), jobs, False)
    assert accepted
    assert "| node | selected; live credentials withheld | success |" in summary


def test_partial_reruns_keep_successful_siblings_without_using_old_failures() -> None:
    from tests.scripts.test_ci_staging_scope import workflow

    (read,) = workflow("ci.yml")["jobs"]["job-results"]["steps"]
    assert "jobs?filter=latest&per_page=100" in read["run"]
    assert "/attempts/" not in read["run"]
    results = needs({"paired_live": True, "paired_shards": ["1/2", "2/2"]})
    jobs: list[Job] = [
        {"name": "paired / live (1/2)", "conclusion": "success"},
        {"name": "paired / live (2/2)", "conclusion": "success"},
    ]
    assert report(results, jobs, True)[1]
    jobs[1]["conclusion"] = "failure"
    assert not report(results, jobs, True)[1]


@pytest.mark.parametrize("api_status", [0, 7])
def test_workflow_collects_all_job_pages_and_propagates_api_errors(tmp_path: Path, api_status: int) -> None:
    from tests.scripts.test_ci_staging_scope import workflow

    jobs_by_id = workflow("ci.yml")["jobs"]
    collector = jobs_by_id["job-results"]
    # The Actions-read token never reaches a job that checks out or runs PR code.
    assert collector["permissions"] == {"actions": "read"}
    assert all("uses" not in step for step in collector["steps"])
    assert "actions" not in jobs_by_id["tests"]["permissions"]
    assert "job-results" in jobs_by_id["tests"]["needs"]
    (step,) = collector["steps"]
    assert step["shell"] == "bash"
    jobs = [
        {"name": "node / tests (22)", "conclusion": "success"},
        {"name": "node / integration-tests", "conclusion": "failure"},
    ]
    (tmp_path / "pages.json").write_text(json.dumps([{"jobs": [job]} for job in jobs]))
    stub = tmp_path / "gh"
    stub.write_text('#!/bin/sh\ncat "$RUNNER_TEMP/pages.json"\nexit "$API_STATUS"\n')
    stub.chmod(0o755)
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_REPOSITORY": "fixture/repo",
            "GITHUB_RUN_ID": "123",
            "API_STATUS": str(api_status),
            "GITHUB_OUTPUT": str(tmp_path / "output"),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == api_status, result.stdout + result.stderr
    name, separator, value = (tmp_path / "output").read_text().strip().partition("=")
    assert (name, separator) == ("jobs", "=")
    assert json.loads(value) == jobs
