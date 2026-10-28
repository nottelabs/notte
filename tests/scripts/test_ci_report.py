"""Exercise missing coverage and separate CI failure reporting."""

import json

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
        {"name": "python / llm-provider-matrix", "conclusion": "skipped"},
    ]
    summary, _ = report(needs({"node_live": True}), jobs, True)
    assert "## Code correctness\n\n| Job | Result |\n| --- | --- |\n| python / tests (3.15) | success |" in summary
    assert (
        "## Staging integrations\n\n| Job | Result |\n| --- | --- |\n| node / integration-tests | failure |" in summary
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

    job = workflow("ci.yml")["jobs"]["tests"]
    read = next(step for step in job["steps"] if step.get("name") == "Read latest job results for this run")
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
