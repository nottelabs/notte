"""Keep staging coordination out of independent CI checks."""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import ci_scope

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github/workflows"


def workflow(name: str) -> dict[str, Any]:
    return yaml.safe_load((WORKFLOWS / name).read_text())


def test_shared_queue_only_contains_staging_test_jobs() -> None:
    expected = {
        ("claude-agents-integration.yml", "live"),
        ("openai-agents-integration.yml", "live"),
        ("github-actions-integration.yml", "live"),
        ("node-sdk-ci.yml", "integration-tests"),
        ("test-cicd.yml", "staging-and-live"),
        ("docs-tests-cicd.yml", "execution"),
        ("paired-sdk-examples.yml", "live"),
        ("readme-check.yml", "live"),
        ("agent-browser-integration.yml", "live"),
        ("trigger-integration.yml", "browser-handler"),
        ("temporal-integration.yml", "browser-workflow"),
        ("inngest-integration.yml", "live"),
        ("docker-sandboxes-integration.yml", "live"),
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
    assert jobs["syntax-check"]["needs"] == "changes"
    assert jobs["type-check"]["needs"] == "changes"
    assert set(jobs["execution"]["needs"]) == {"changes", "syntax-check", "type-check"}


def test_unit_suite_never_waits_for_or_cleans_up_staging() -> None:
    jobs = workflow("test-cicd.yml")["jobs"]
    offline = jobs["tests"]
    live = jobs["staging-and-live"]
    assert "concurrency" not in offline
    assert "${{ secrets." not in str(offline)
    assert "Wait for the API to be ready" not in str(offline)
    assert "Cleanup vaults created by this run" not in str(offline)
    assert "make test-cicd" in str(offline)
    assert '-m "staging or live"' in str(live)
    steps = {step.get("name"): step for step in live["steps"]}
    assert steps["Wait for the API to be ready"]["uses"] == "./.github/actions/wait-for-api"
    assert steps["Cleanup vaults created by this run"]["if"] == "${{ always() }}"
    assert "secrets.NOTTE_API_KEY" in str(steps["Run staging and live tests"])


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


def triggers(config: dict[str, Any]) -> dict[str, Any]:
    # PyYAML's YAML 1.1 parser reads the unquoted GitHub Actions `on` key as True.
    return config.get("on", config.get(True))


def test_automatic_selection_runs_once_with_complete_history() -> None:
    config = workflow("ci.yml")
    assert set(triggers(config)) == {"push", "pull_request"}
    assert config["permissions"] == {"contents": "read"}
    assert triggers(config)["push"] == {"branches": ["main"]}
    assert triggers(config)["pull_request"] == {"branches": ["main"]}
    changes = config["jobs"]["changes"]
    assert "concurrency" not in changes
    checkout = next(step for step in changes["steps"] if "checkout@" in step.get("uses", ""))
    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["persist-credentials"] is False
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.head.sha || github.sha }}"
    assert sum(step.get("uses") == "./.github/actions/ci-scope" for step in changes["steps"]) == 1
    assert "secrets." not in str(changes)


def test_only_selected_families_receive_the_shared_scope() -> None:
    jobs = workflow("ci.yml")["jobs"]
    for name, family in ci_scope.WORKFLOWS.items():
        job = jobs[family]
        assert job["needs"] == "changes"
        assert job["uses"] == f"./.github/workflows/{name}"
        expected_inputs = {"scope": "${{ needs.changes.outputs.scope }}"}
        if family == "python":
            expected_inputs.update(
                source_sha="${{ needs.changes.outputs.source_sha }}",
                llm_provider="${{ needs.changes.outputs.llm_provider }}",
            )
        assert job["with"] == expected_inputs
        assert job["secrets"] == "inherit"  # pragma: allowlist secret
        keys = set(re.findall(r"fromJSON\(needs.changes.outputs.scope\)\.(\w+)", job["if"]))
        assert keys == ci_scope.GROUPS[family] | ({"file_checks"} if family == "python" else set())
    assert jobs["python"]["permissions"] == {"contents": "read", "pull-requests": "write"}


def test_reusable_suites_reuse_scope_and_keep_standalone_selection() -> None:
    for name in ci_scope.WORKFLOWS:
        config = workflow(name)
        events = triggers(config)
        assert "push" not in events and "pull_request" not in events
        assert "workflow_dispatch" in events
        assert events["workflow_call"]["inputs"]["scope"] == {
            "description": "Suite decisions from the shared push or PR selector.",
            "type": "string",
            "default": "",
        }
        jobs = config["jobs"]
        changes = jobs["changes"]
        assert "concurrency" not in changes
        assert changes["outputs"]["scope"] == "${{ inputs.scope || steps.scope.outputs.scope }}"
        validation = changes["steps"][0]
        assert validation["if"] == "inputs.scope != ''"
        # Node's normal working directory does not exist without a checkout.
        assert validation["working-directory"] == "${{ github.workspace }}"
        assert validation["env"] == {"SCOPE": "${{ inputs.scope }}"}
        checkout = next(step for step in changes["steps"] if "checkout@" in step.get("uses", ""))
        assert checkout["if"] == "inputs.scope == ''"
        assert checkout["with"]["fetch-depth"] == 0
        assert checkout["with"]["persist-credentials"] is False
        selector = next(step for step in changes["steps"] if step.get("uses") == "./.github/actions/ci-scope")
        assert selector["if"] == "inputs.scope == ''"
        for job_id, job in jobs.items():
            if job_id == "changes":
                continue
            needs = job.get("needs", [])
            if isinstance(needs, str):
                needs = [needs]
            assert "changes" in needs, (name, job_id)
            assert "fromJSON(needs.changes.outputs.scope)" in job["if"], (name, job_id)


def test_periodic_coverage_and_cancellation_boundaries_are_preserved() -> None:
    assert "concurrency" not in workflow("ci.yml")
    for name in ci_scope.WORKFLOWS:
        config = workflow(name)
        if name in {"test-cicd.yml", "node-sdk-ci.yml"}:
            assert triggers(config)["schedule"] == [{"cron": "0 */4 * * 1-5"}]
            assert config["concurrency"]["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"
        else:
            assert "concurrency" not in config
            assert "schedule" not in triggers(config)
    inputs = triggers(workflow("test-cicd.yml"))["workflow_dispatch"]["inputs"]
    assert inputs["pr_number"]["required"] is True
    assert "llm_provider" not in inputs  # Paid dispatch requires the coordinating SHA validation.


def test_live_selection_does_not_bypass_fork_protection() -> None:
    for name, job_id in (
        ("node-sdk-ci.yml", "integration-tests"),
        ("test-cicd.yml", "staging-and-live"),
        ("docs-tests-cicd.yml", "execution"),
        ("paired-sdk-examples.yml", "live"),
        ("readme-check.yml", "live"),
    ):
        condition = workflow(name)["jobs"][job_id]["if"]
        assert "github.event.pull_request.head.repo.full_name == github.repository" in condition
        assert "fromJSON(needs.changes.outputs.scope)" in condition
        assert "ci-reviewed/" not in condition


def test_lightweight_docs_assertions_have_no_workspace_or_secrets() -> None:
    job = workflow("test-cicd.yml")["jobs"]["docs"]
    assert job["permissions"] == {"contents": "read"}
    assert "github.event_name == 'push' || github.event_name == 'pull_request'" in job["if"]
    assert "pr_number" not in str(job)
    assert "secrets." not in str(job)
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert "pytest -c /dev/null" in commands
    assert "tests/docs tests/test_generate_llms_offline.py --noconftest" in commands
    assert "pytest pyyaml" in commands
    assert "uv sync" not in commands


def test_deleted_docs_still_run_the_global_link_check() -> None:
    steps = workflow("test-cicd.yml")["jobs"]["checks"]["steps"]
    step = next(step for step in steps if step.get("name") == "Run pre-commit")
    assert step["env"]["DOCS_LINKS"] == "${{ fromJSON(needs.changes.outputs.scope).docs_links }}"
    assert 'if [ "$DOCS_LINKS" = true ]' in step["run"]
    assert '"${runner[@]}" run check-docs-broken-links --all-files' in step["run"]


@pytest.mark.parametrize(
    "changes,selected,expected",
    [
        ("success", "success", 0),
        ("success", "skipped", 0),
        ("success", "failure", 1),
        ("success", "cancelled", 1),
        ("skipped", "success", 1),
        ("failure", "success", 1),
        ("cancelled", "success", 1),
    ],
)
@pytest.mark.parametrize("family", ["node", "paired"])
def test_required_gate_waits_for_all_families_and_fails_closed(
    changes: str, selected: str, expected: int, family: str
) -> None:
    job = workflow("ci.yml")["jobs"]["tests"]
    assert job["if"] == "always()"
    assert set(job["needs"]) == {"changes", *ci_scope.GROUPS}
    results = {name: {"result": "skipped"} for name in job["needs"]}
    results["changes"]["result"] = changes
    results[family]["result"] = selected
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", job["steps"][0]["run"]],
        env={**os.environ, "RESULTS": json.dumps(results)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected, result.stdout + result.stderr


def test_native_examples_have_one_existing_required_owner() -> None:
    assert not (WORKFLOWS / "openai-computer-use-integration.yml").exists()
    jobs = workflow("paired-sdk-examples.yml")["jobs"]
    assert set(jobs) == {"changes", "checks", "live"}
    assert set(jobs["live"]["needs"]) == {"changes", "checks"}
    snippet = next(s for s in jobs["live"]["steps"] if "test/docs-snippets.integration.test.ts" in s.get("run", ""))
    assert snippet["if"] == "fromJSON(needs.changes.outputs.scope).paired_snippets_live"
    for name, phase in (("checks", "checks"), ("live", "live")):
        job = jobs[name]
        assert all(s["with"]["node-version"] == "24" for s in job["steps"] if "setup-node@" in s.get("uses", ""))
        steps = [s for s in job["steps"] if "scripts/ci_integration_examples.py" in s.get("run", "")]
        assert len(steps) == 1
        step = steps[0]
        assert f"ci_integration_examples.py {phase}" in step["run"]
        assert "integration_examples" in step["env"]["INTEGRATION_EXAMPLES"]
        assert not step.get("continue-on-error") and not job.get("continue-on-error")
        if phase == "checks":
            assert "secrets." not in str(step)
        else:
            assert '--shard "$NOTTE_DOCS_SHARD"' in step["run"]
            for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
                assert "github.ref == 'refs/heads/main' && github.event_name != 'pull_request'" in step["env"][key]


def test_scoped_checks_fetch_history_only_during_authenticated_checkout() -> None:
    job = workflow("test-cicd.yml")["jobs"]["checks"]
    checkouts = [step for step in job["steps"] if "checkout@" in step.get("uses", "")]
    assert len(checkouts) == 2
    for step in checkouts:
        assert step["with"]["fetch-depth"] == 0
        assert step["with"]["persist-credentials"] is False
    lint = next(step for step in job["steps"] if step.get("name") == "Run pre-commit")
    assert "git fetch" not in lint["run"]


@pytest.mark.parametrize(
    "event,attempt,label,fork,moved,expected",
    [
        ("pull_request", 1, True, False, False, "gemini"),
        ("pull_request", 2, True, False, False, "openai"),
        ("pull_request", 2, False, False, False, "gemini"),
        ("pull_request", 2, True, True, False, "gemini"),
        ("pull_request", 2, True, False, True, None),
        ("push", 1, True, False, False, "openai"),
        ("push", 1, False, False, False, "gemini"),
    ],
)
def test_provider_selection_executes_the_normal_workflow(
    tmp_path: Path, event: str, attempt: int, label: bool, fork: bool, moved: bool, expected: str | None
) -> None:
    step = next(s for s in workflow("ci.yml")["jobs"]["changes"]["steps"] if s.get("id") == "provider")
    pull = {
        "state": "open" if event == "pull_request" else "closed",
        "merged_at": None if event == "pull_request" else "2026-10-16T00:00:00Z",
        "merge_commit_sha": "a" * 40,
        "base": {"ref": "main", "repo": {"full_name": "owner/repo"}},
        "head": {"sha": ("b" if moved else "a") * 40, "repo": {"full_name": "owner/repo"}},
        "labels": [{"name": "ci:openai"}] if label else [],
        "user": {"login": "fixture-maintainer"},
    }
    response = tmp_path / "response.json"
    response.write_text(json.dumps(pull if event == "pull_request" else [pull]))
    stub = tmp_path / "gh"
    stub.write_text("""#!/usr/bin/env python3
import os, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
Path(os.environ["CALLED"]).write_text(args[1])
sys.exit(subprocess.run(["jq", args[args.index("--jq") + 1]], stdin=open(os.environ["RESPONSE"])).returncode)
""")
    stub.chmod(0o755)
    output = tmp_path / "outputs"
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=WORKFLOWS.parents[1],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "EVENT_NAME": event,
            "GITHUB_REF": "refs/heads/main" if event == "push" else "refs/pull/1214/merge",
            "GITHUB_RUN_ATTEMPT": str(attempt),
            "SOURCE_SHA": "a" * 40,
            "PR_NUMBER": "1214",
            "SAME_REPOSITORY": "false" if fork else "true",
            "DELETED": "false",
            "RESPONSE": str(response),
            "CALLED": str(tmp_path / "called"),
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(output),
            "GITHUB_REPOSITORY": "owner/repo",
        },
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) == (expected is not None), result.stdout + result.stderr
    assert (tmp_path / "called").exists() is not fork
    if expected is not None:
        assert output.read_text() == f"provider={expected}\nsource_sha={'a' * 40}\n"
        assert (tmp_path / "ci-provider-pulls.json").stat().st_mode & 0o077 == 0


@pytest.mark.parametrize(
    "provider,key,source_matches,checkout_matches,succeeds",
    [
        ("gemini", "", True, True, True),
        ("openai", "dummy-test-key", True, True, True),
        ("openai", "", True, True, False),
        ("unknown", "", True, True, False),
        ("openai", "dummy-test-key", False, True, False),
        ("openai", "dummy-test-key", True, False, False),
    ],
)
def test_selected_provider_runs_the_full_live_suite(
    tmp_path: Path, provider: str, key: str, source_matches: bool, checkout_matches: bool, succeeds: bool
) -> None:
    step = next(
        s
        for s in workflow("test-cicd.yml")["jobs"]["staging-and-live"]["steps"]
        if s.get("name") == "Run staging and live tests"
    )
    paid_key = step["env"]["OPENAI_API_KEY"]
    assert "github.event.pull_request.head.repo.full_name == github.repository && github.run_attempt > 1" in paid_key
    assert "inputs.source_sha == (github.event.pull_request.head.sha || github.sha)" in paid_key
    assert "github.event_name == 'push' && github.ref == 'refs/heads/main' && !github.event.deleted" in paid_key
    output = tmp_path / "invocation.json"
    stub = tmp_path / "make"
    stub.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
Path(os.environ["OUTPUT"]).write_text(json.dumps({
    "args": sys.argv[1:], "url": os.environ["NOTTE_LLM_BASE_URL"],
    "model": os.environ["NOTTE_LLM_MODEL"], "default": os.environ["NOTTE_TEST_DEFAULT_MODEL"],
    "key_matches": os.environ["NOTTE_LLM_API_KEY"] == os.environ["OPENAI_API_KEY"]}))
""")
    stub.chmod(0o755)
    git = tmp_path / "git"
    git.write_text('#!/bin/sh\ntest "$*" = "rev-parse HEAD" || exit 1\nprintf "%s\\n" "$CHECKED_OUT_SHA"\n')
    git.chmod(0o755)
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "OUTPUT": str(output),
            "NOTTE_CI_LLM_PROVIDER": provider,
            "NOTTE_CI_SOURCE_SHA": "a" * 40 if source_matches else "",
            "NOTTE_CI_EXPECTED_SHA": "a" * 40,
            "CHECKED_OUT_SHA": ("a" if checkout_matches else "c") * 40,
            "GITHUB_SHA": "b" * 40,  # The PR's synthetic merge SHA differs from its actual source.
            "OPENAI_API_KEY": key,
            "NOTTE_LLM_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai",
            "NOTTE_LLM_MODEL": "gemini-3.5-flash-lite",
            "NOTTE_TEST_DEFAULT_MODEL": "gemini-3.5-flash-lite",
            "NOTTE_LLM_API_KEY": "dummy-gemini-key",  # pragma: allowlist secret
        },
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) == succeeds, result.stdout + result.stderr
    assert output.exists() == succeeds
    if succeeds:
        invocation = json.loads(output.read_text())
        assert invocation["args"][0] == "test-live"
        assert '-m "staging or live"' in invocation["args"][1]
        if provider == "openai":
            assert invocation["url"] == "https://api.openai.com/v1"
            assert invocation["model"] == "gpt-4.1-mini"
            assert invocation["default"] == "gpt-4.1-nano"
            assert invocation["key_matches"] is True
        else:
            assert invocation["model"] == "gemini-3.5-flash-lite"
            assert invocation["key_matches"] is False


@pytest.mark.parametrize("base", ["a" * 40, "0" * 40, ""])
def test_parity_uses_the_actual_comparison_base(tmp_path: Path, base: str) -> None:
    step = next(
        s
        for s in workflow("paired-sdk-examples.yml")["jobs"]["checks"]["steps"]
        if s.get("name") == "Enforce example parity and shrinking backlog"
    )
    assert step["env"]["BASE_SHA"] == "${{ github.event.pull_request.base.sha || github.event.before }}"
    stub = tmp_path / "python"
    output = tmp_path / "args"
    stub.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$OUTPUT"\n')
    stub.chmod(0o755)
    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        check=True,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "BASE_SHA": base, "OUTPUT": str(output)},
    )
    expected = ["docs/src/sniptest/parity.py"]
    if base and set(base) != {"0"}:
        expected += ["--base-ref", base]
    assert output.read_text().splitlines() == expected


@pytest.mark.parametrize(
    "python_setup,full,docs_links", [(False, False, False), (True, False, True), (True, True, False)]
)
def test_file_checks_use_the_selected_environment(
    tmp_path: Path, python_setup: bool, full: bool, docs_links: bool
) -> None:
    job = workflow("test-cicd.yml")["jobs"]["checks"]
    assert job["if"] == "fromJSON(needs.changes.outputs.scope).file_checks"
    step = next(step for step in job["steps"] if step.get("name") == "Run pre-commit")
    stub = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
with open(os.environ['COMMAND_LOG'], 'a') as log:
    log.write(json.dumps([Path(sys.argv[0]).name, *sys.argv[1:]]) + '\\n')
"""
    for executable in ("uv", "uvx", "git"):
        path = tmp_path / executable
        path.write_text(stub)
        path.chmod(0o755)
    output = tmp_path / "commands.jsonl"
    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        check=True,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "COMMAND_LOG": str(output),
            "FULL": str(full).lower(),
            "PYTHON_SETUP": str(python_setup).lower(),
            "DOCS_LINKS": str(docs_links).lower(),
            "BASE_SHA": "a" * 40,
            "HEAD_SHA": "b" * 40,
        },
    )
    calls = [json.loads(line) for line in output.read_text().splitlines()]
    runner = (
        ["uv", "run", "--active", "pre-commit"]
        if python_setup
        else ["uvx", "--from", "pre-commit==4.6.2", "pre-commit"]
    )
    if full:
        assert calls == [[*runner, "run", "--all-files"]]
    else:
        assert calls[:1] == [[*runner, "run", "--from-ref", "a" * 40, "--to-ref", "b" * 40]]
        if docs_links:
            assert calls[1] == [*runner, "run", "check-docs-broken-links", "--all-files"]
