"""The OpenAPI refresh starts again on main once its PR closes, with no GitHub calls."""

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts import complete_bot_pr as bot

ROOT = Path(__file__).resolve().parents[2]
RESUME = ROOT / ".github/workflows/openapi-bump-resume.yml"
BUMP = ROOT / ".github/workflows/openapi-bump.yml"

spec = importlib.util.spec_from_file_location("openapi_contract", ROOT / "scripts/openapi_contract.py")
assert spec and spec.loader
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def workflow() -> dict:
    return yaml.safe_load(RESUME.read_text())


def step(name: str) -> dict:
    [found] = [item for item in workflow()["jobs"]["resume"]["steps"] if item["name"] == name]
    return found


def fake(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(f'#!/usr/bin/env bash\necho "{name} $*" >> "$CALLS"\n{body}\n')
    path.chmod(0o755)


def run_step(name: str, tmp_path: Path, **env: str) -> tuple[subprocess.CompletedProcess[str], str, str]:
    """Run one step's script with fake `gh`, `git` and `uv`; return the result, its outputs and the calls."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    # Each fake prints what its `--jq` filter would have returned.
    fake(bin_dir, "gh", 'case "$1 $2" in "pr list") echo "$FAKE_PR" ;; "run list") echo "$FAKE_PENDING" ;; esac')
    fake(bin_dir, "git", 'if [ "$1" = show ]; then echo "{}"; fi')
    fake(bin_dir, "uv", 'exit "$FAKE_UV_STATUS"')
    output, calls = tmp_path / "output", tmp_path / "calls"
    output.write_text("")
    calls.write_text("")
    defaults = {"FAKE_PR": "", "FAKE_PENDING": "0", "FAKE_UV_STATUS": "0"}
    result = subprocess.run(
        ["bash", "-c", step(name)["run"]],
        env={
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "CALLS": str(calls),
            "GITHUB_OUTPUT": str(output),
            "GITHUB_REPOSITORY": bot.REPOSITORY,
            "RUNNER_TEMP": str(tmp_path),
            **workflow()["jobs"]["resume"]["env"],
            **defaults,
            **env,
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result, output.read_text(), calls.read_text()


def test_triggers_cover_a_closed_refresh_pr_and_main_changes():
    triggers = workflow()[True]
    assert set(triggers) == {"push", "pull_request_target", "schedule", "workflow_dispatch"}
    assert triggers["push"]["branches"] == ["main"]
    for path in (
        "openapi/openapi.json",
        ".github/workflows/openapi-bump.yml",
        ".github/workflows/openapi-bump-resume.yml",
    ):
        assert path in triggers["push"]["paths"]
    for path in triggers["push"]["paths"]:
        assert (ROOT / path).is_file()
    assert triggers["pull_request_target"] == {"types": ["closed"], "branches": ["main"]}
    assert triggers["schedule"]


def test_runs_trusted_main_code_only_and_writes_nothing_but_a_dispatch():
    resume = workflow()
    job = resume["jobs"]["resume"]
    assert resume["permissions"] == {"contents": "read"}
    # Job-level, so a skipped run for an unrelated PR never takes the pending slot.
    assert "concurrency" not in resume
    assert job["concurrency"] == {"group": "resume-bump-openapi", "cancel-in-progress": False}
    assert job["permissions"] == {"actions": "write", "contents": "read", "pull-requests": "read"}
    condition = " ".join(job["if"].split())
    assert "github.repository == 'nottelabs/notte' && github.ref == 'refs/heads/main'" in condition
    assert "github.event.pull_request.head.ref == 'chore/bump-openapi'" in condition
    assert "github.event.pull_request.head.repo.full_name == github.repository" in condition
    assert step("Checkout main")["with"] == {"ref": "main", "persist-credentials": False}
    text = RESUME.read_text()
    assert "secrets." not in text
    assert "github.event.pull_request.head.sha" not in text
    assert "gh pr merge" not in text and "git push" not in text


def test_matches_the_refresh_it_starts():
    bump = yaml.safe_load(BUMP.read_text())["jobs"]["bump"]["env"]
    env = workflow()["jobs"]["resume"]["env"]
    assert env == {"BRANCH": bump["BRANCH"], "SCHEMA_BRANCH": bump["SCHEMA_BRANCH"]}
    assert bot.PRODUCERS[env["BRANCH"]] == ".github/workflows/openapi-bump.yml"
    # complete-bot-pr only accepts a refresh run dispatched (or scheduled) on main.
    assert "workflow_dispatch" in yaml.safe_load(BUMP.read_text())[True]
    assert "workflow_dispatch" in bot.producers(env["BRANCH"])[0]["events"]


@pytest.mark.parametrize(("pr", "expected"), [("", "open=false"), ("1663", "open=true")])
def test_an_open_refresh_pr_is_left_to_the_refresh(tmp_path: Path, pr: str, expected: str):
    result, output, calls = run_step("Check for an open refresh PR", tmp_path, FAKE_PR=pr)
    assert result.returncode == 0, result.stderr
    assert output == f"{expected}\n"
    assert "--head chore/bump-openapi --base main --state open" in calls
    later = workflow()["jobs"]["resume"]["steps"][1:]
    assert all(item["if"] == "steps.pr.outputs.open == 'false'" for item in later[:-1])


@pytest.mark.parametrize(
    ("status", "expected"), [(0, "outdated=false\n"), (contract.OUTDATED, "outdated=true\n"), (1, "")]
)
def test_compares_with_the_refresh_dry_run(tmp_path: Path, status: int, expected: str):
    result, output, calls = run_step(
        "Compare the published schema with main's snapshot", tmp_path, FAKE_UV_STATUS=str(status)
    )
    assert result.returncode == (1 if status == 1 else 0)
    assert output == expected
    assert "git fetch --quiet --depth=1 origin refs/heads/openapi-schema" in calls
    assert (tmp_path / "schema/openapi.json").read_text() == "{}\n"
    assert (
        f"uv run --frozen --no-dev --package notte-core python scripts/openapi_contract.py "
        f"--fetch --dry-run --url file://{tmp_path}/schema"
    ) in calls


@pytest.mark.parametrize(("pending", "pr", "dispatched"), [("0", "", True), ("1", "", False), ("0", "1669", False)])
def test_starts_the_refresh_on_main_unless_one_is_pending_or_open(
    tmp_path: Path, pending: str, pr: str, dispatched: bool
):
    name = "Start the refresh on main"
    assert step(name)["if"] == "steps.compare.outputs.outdated == 'true'"
    result, _, calls = run_step(name, tmp_path, FAKE_PENDING=pending, FAKE_PR=pr)
    assert result.returncode == 0, result.stderr
    assert "gh run list --repo nottelabs/notte --workflow openapi-bump.yml" in calls
    assert ("gh workflow run openapi-bump.yml --repo nottelabs/notte --ref main" in calls) is dispatched
