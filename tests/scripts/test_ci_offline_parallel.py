"""Keep both offline dependency suites independent and required."""

import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest

from tests.scripts.test_ci_staging_scope import workflow


def test_dependency_suites_start_independently_without_credentials() -> None:
    jobs = workflow("test-cicd.yml")["jobs"]
    for name in ("tests", "compatible-dependencies"):
        job = jobs[name]
        assert job["needs"] == "changes"
        assert "fromJSON(needs.changes.outputs.scope).python_unit" in job["if"]
        assert job["runs-on"] == "blacksmith-4vcpu-ubuntu-2404"
        assert job["timeout-minutes"] == 20
        assert "concurrency" not in job
        assert re.search(r"\bsecrets\.\w+", str(job)) is None
        assert not job.get("continue-on-error")
        assert all(not step.get("continue-on-error") for step in job["steps"])

    compatible = jobs["compatible-dependencies"]
    assert compatible["permissions"] == {"contents": "read"}
    setup = next(step for step in compatible["steps"] if step.get("uses") == "./.github/actions/python-setup")
    assert setup["with"] == {"browsers": "true", "python-version": "3.15"}
    checkouts = [step for step in compatible["steps"] if "checkout@" in step.get("uses", "")]
    assert len(checkouts) == 1
    assert checkouts[0]["with"]["ref"] == "${{ github.event.pull_request.head.sha || github.sha }}"
    assert checkouts[0]["with"]["persist-credentials"] is False
    assert "pr_number" not in str(compatible)
    assert "github.event.inputs" not in str(compatible)

    # The caller requires the entire reusable workflow, including both jobs.
    caller = workflow("ci.yml")["jobs"]
    assert caller["python"]["uses"] == "./.github/workflows/test-cicd.yml"
    assert not caller["python"].get("continue-on-error")
    assert "python_unit" in caller["python"]["if"]
    assert "python" in caller["tests"]["needs"]
    assert caller["tests"]["if"] == "always()"


def test_suite_selection_and_coverage_ownership_are_preserved() -> None:
    jobs = workflow("test-cicd.yml")["jobs"]
    locked = jobs["tests"]
    assert locked["strategy"] == {"fail-fast": False, "matrix": {"python": ["3.15", "3.11"]}}
    steps = {step.get("name"): step for step in locked["steps"]}
    assert steps["Run full unit suite"]["if"] == "matrix.python == '3.15'"
    assert steps["Run full unit suite"]["run"] == "set -o pipefail\nmake test-cicd | tee pytest-coverage.txt\n"
    for name, command in (
        ("Check Python 3.11 compatibility", "make test-compat"),
        ("Run duration bounds one at a time", "make test-timing"),
    ):
        assert steps[name]["if"] == "matrix.python == '3.11'"
        assert steps[name]["run"] == command
    assert "Test compatible dependency versions" not in steps

    compatible = jobs["compatible-dependencies"]
    command = next(step["run"] for step in compatible["steps"] if "run" in step)
    assert steps["Test compatible dependency versions (manual trigger)"]["run"] == command
    assert shlex.split(command) == [
        "uv",
        "run",
        "--with",
        "websockets==15.0.1",
        "--with",
        "beautifulsoup4==4.14.3",
        "--with",
        "posthog==7.0.1",
        "pytest",
        "-n",
        "logical",
        "tests/sdk",
        "tests/browser",
        "tests/llm",
        "tests/data",
        "tests/test_telemetry.py",
        "tests/test_telemetry_delivery.py",
        "-m",
        "not staging and not live and not timing",
        "-q",
    ]
    assert "coverage" not in str(compatible)
    comments = [
        (job_id, step)
        for job_id, job in jobs.items()
        for step in job.get("steps", [])
        if "pytest-coverage-comment@" in step.get("uses", "")
    ]
    assert len(comments) == 1
    owner, comment = comments[0]
    assert owner == "tests"
    assert "matrix.python == '3.15'" in comment["if"]
    assert comment["with"] == {"pytest-coverage-path": "./pytest-coverage.txt", "junitxml-path": "./pytest.xml"}


@pytest.mark.parametrize("event", ["pull_request", "push", "schedule", "workflow_dispatch"])
@pytest.mark.parametrize("python_version", ["3.15", "3.11"])
@pytest.mark.parametrize("selected", [True, False])
def test_event_boundary_keeps_exactly_one_compatible_suite(event: str, python_version: str, selected: bool) -> None:
    jobs = workflow("test-cicd.yml")["jobs"]
    manual = next(
        step
        for step in jobs["tests"]["steps"]
        if step.get("name") == "Test compatible dependency versions (manual trigger)"
    )
    # These conditions use only string equality and conjunction, shared by Bash
    # and Actions. Exercise the actual YAML conditions against each event/scope.
    expressions = {
        "independent": jobs["compatible-dependencies"]["if"],
        "manual": f"{jobs['tests']['if']} && {manual['if']}",
    }
    decisions = {}
    for name, expression in expressions.items():
        expression = (
            expression.replace("fromJSON(needs.changes.outputs.scope).python_unit", '"$SELECTED" == true')
            .replace("github.event_name", '"$EVENT_NAME"')
            .replace("matrix.python", '"$PYTHON_VERSION"')
        )
        result = subprocess.run(
            ["bash", "-c", f"[[ {expression} ]]"],
            env={
                **os.environ,
                "EVENT_NAME": event,
                "PYTHON_VERSION": python_version,
                "SELECTED": str(selected).lower(),
            },
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode in (0, 1), result.stderr
        decisions[name] = result.returncode == 0
    assert decisions == {
        "independent": selected and event != "workflow_dispatch",
        "manual": selected and event == "workflow_dispatch" and python_version == "3.15",
    }
    # Both fork and same-repository PRs keep the automatic, credential-free gate.
    assert "head.repo" not in expressions["independent"]
    assert "IS_TRUSTED" not in expressions["independent"]


@pytest.mark.parametrize(
    "job_id,step_name",
    [
        ("tests", "Run full unit suite"),
        ("tests", "Test compatible dependency versions (manual trigger)"),
        ("compatible-dependencies", "Test compatible dependency versions"),
    ],
)
@pytest.mark.parametrize("exit_code", [0, 23])
def test_either_dependency_suite_propagates_command_failure(
    tmp_path: Path, job_id: str, step_name: str, exit_code: int
) -> None:
    job = workflow("test-cicd.yml")["jobs"][job_id]
    step = next(step for step in job["steps"] if step.get("name") == step_name)
    for name in ("make", "uv"):
        stub = tmp_path / name
        stub.write_text('#!/bin/sh\nexit "$SUITE_EXIT_CODE"\n')
        stub.chmod(0o755)
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "SUITE_EXIT_CODE": str(exit_code)},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == exit_code, result.stdout + result.stderr
