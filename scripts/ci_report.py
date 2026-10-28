"""Report selected CI coverage and latest individual job outcomes across a workflow run."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import TypedDict, cast

from scripts.ci_scope import GROUPS


class Need(TypedDict):
    result: str
    outputs: dict[str, str]


class Job(TypedDict):
    name: str
    conclusion: str | None


def report(needs: dict[str, Need], jobs: list[Job], trusted: bool) -> tuple[str, bool]:
    scope = cast(dict[str, bool | list[str]], json.loads(needs["changes"]["outputs"].get("scope") or "{}"))
    complete = needs["changes"]["result"] == "success" and bool(scope)
    lines = ["## CI coverage", "", "| Suite | Selection | Result |", "| --- | --- | --- |"]
    for family, flags in GROUPS.items():
        selected = any(scope.get(flag) is True for flag in flags)
        if family == "python":
            selected |= scope.get("file_checks") is True
        result = needs[family]["result"]
        # A selected family can be entirely credentialed (for example a live-only
        # test change in a fork). Such a run is explicitly incomplete, not verified.
        excluded = selected and result == "skipped" and not trusted
        selection = "credentials withheld" if excluded else "selected" if selected else "outside this diff"
        lines.append(f"| {family} | {selection} | {result} |")
        complete &= result not in {"failure", "cancelled"} and (not selected or result == "success" or excluded)

    sections: dict[str, list[Job]] = defaultdict(list)
    for job in jobs:
        family, separator, name = job["name"].partition(" / ")
        if not separator or family not in GROUPS or name == "changes":
            continue
        if name == "llm-provider-matrix":
            section = "Provider behavior"
        elif name.startswith(("staging-and-live", "live", "integration-tests", "execution")):
            section = "Staging integrations"
        else:
            section = "Code correctness"
        sections[section].append(job)

    expected_jobs = {
        "file_checks": ["python / checks"],
        "python_static": ["python / checks"],
        "python_unit": ["python / tests (3.15)", "python / compatibility (3.11)", "python / compatible-dependencies"],
        "python_docs": ["python / docs"],
        "node_static": ["node / tests (22)", "node / tests (24)"],
        "node_generated": ["node / generated"],
        "docs_static": ["docs / syntax-check", "docs / type-check"],
        "paired_static": ["paired / checks"],
        "readme_static": ["readme / static"],
    }
    if trusted:
        expected_jobs.update(
            {
                "python_live": ["python / staging-and-live (1)", "python / staging-and-live (2)"],
                "llm_provider_live": ["python / llm-provider-matrix"],
                "node_live": ["node / integration-tests"],
                "docs_live": ["docs / execution"],
                "readme_live": ["readme / live"],
            }
        )
    if scope.get("cli_contract") is True:
        expected_jobs["cli_contract"] = [
            "python / cli-contract (ubuntu-24.04, file)",
            "python / cli-contract (ubuntu-24.04, secret-service)",
            "python / cli-contract (macos-15)",
            "python / cli-contract (windows-2025)",
        ]
    successful_jobs = {job["name"] for job in jobs if job["conclusion"] == "success"}
    missing = {
        name
        for flag, names in expected_jobs.items()
        if scope.get(flag) is True
        for name in names
        if name not in successful_jobs
    }
    if missing:
        complete = False
        lines += ["", "Expected jobs without a successful result:", "", *[f"- {name}" for name in sorted(missing)]]

    for section in ("Code correctness", "Staging integrations", "Provider behavior"):
        lines += ["", f"## {section}", "", "| Job | Result |", "| --- | --- |"]
        for job in sorted(sections[section], key=lambda job: job["name"]):
            name = job["name"].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {name} | {job['conclusion'] or 'incomplete'} |")
        if not sections[section]:
            lines.append("| No jobs selected | not evaluated |")

    paired = [job for job in sections["Staging integrations"] if job["name"].startswith("paired / live (")]
    if trusted and scope.get("paired_live") is True:
        expected = {f"paired / live ({shard})" for shard in cast(list[str], scope["paired_shards"])}
        successful = {job["name"] for job in paired if job["conclusion"] == "success"}
        if expected != successful:
            complete = False
            lines += ["", "Incomplete paired coverage: an expected shard did not finish successfully."]
    lines += [
        "",
        "These results cover the selected diff, not a full repository baseline.",
        "Job success can include test retries or skips; test-level reports remain authoritative.",
        "Staging integrations and provider behavior are not independent availability probes.",
    ]
    return "\n".join(lines) + "\n", complete


def main() -> None:
    needs = cast(dict[str, Need], json.loads(os.environ["RESULTS"]))
    jobs = cast(list[Job], json.loads(Path(os.environ["JOBS_PATH"]).read_text()))
    summary, complete = report(needs, jobs, os.environ["TRUSTED_LIVE"] == "true")
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as output:
        _ = output.write(summary)
    if not complete:
        raise SystemExit("Selected CI coverage did not complete successfully")


if __name__ == "__main__":
    main()
