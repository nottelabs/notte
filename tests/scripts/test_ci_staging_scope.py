"""Keep staging coordination out of independent CI checks."""

from pathlib import Path
from typing import Any

import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github/workflows"


def workflow(name: str) -> dict[str, Any]:
    return yaml.safe_load((WORKFLOWS / name).read_text())


def test_shared_queue_only_contains_staging_test_jobs() -> None:
    expected = {
        ("node-sdk-ci.yml", "integration-tests"),
        ("test-cicd.yml", "staging-and-live"),
        ("docs-tests-cicd.yml", "execution"),
        ("paired-sdk-examples.yml", "live"),
        ("readme-check.yml", "live"),
    }
    queued = set()
    for path in WORKFLOWS.glob("*.yml"):
        config = workflow(path.name)
        assert "notte-live-api" not in str(config.get("concurrency", {})), path.name
        for job_id, job in config.get("jobs", {}).items():
            if "notte-live-api" in str(job.get("concurrency", {})):
                queued.add((path.name, job_id))
    assert queued == expected


def test_documentation_checks_start_independently() -> None:
    jobs = workflow("docs-tests-cicd.yml")["jobs"]
    assert not jobs["syntax-check"].get("needs")
    assert not jobs["type-check"].get("needs")
    assert set(jobs["execution"]["needs"]) == {"syntax-check", "type-check"}


def test_unit_suite_never_waits_for_or_cleans_up_staging() -> None:
    jobs = workflow("test-cicd.yml")["jobs"]
    assert "concurrency" not in jobs["tests"]
    for step in jobs["tests"]["steps"]:
        assert "wait-for-api" not in str(step)
        assert "cleanup_ci_vaults" not in str(step)
        assert "NOTTE_API_KEY" not in step.get("env", {})


def test_independent_checks_never_depend_on_staging_jobs() -> None:
    for name, staging_jobs in {
        "node-sdk-ci.yml": {"integration-tests"},
        "test-cicd.yml": {"staging-and-live"},
        "docs-tests-cicd.yml": {"execution"},
        "paired-sdk-examples.yml": {"live"},
        "readme-check.yml": {"live"},
    }.items():
        for job_id, job in workflow(name)["jobs"].items():
            # The aggregate result must wait for every selected suite.
            if job_id in staging_jobs or (name == "test-cicd.yml" and job_id == "tests"):
                continue
            needs = job.get("needs", [])
            if isinstance(needs, str):
                needs = [needs]
            assert not staging_jobs.intersection(needs), (name, job_id)
