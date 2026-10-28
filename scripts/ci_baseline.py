"""Check freshness and job completeness of the full scheduled examples run."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict, cast


class Run(TypedDict):
    id: int
    head_sha: str
    head_branch: str
    event: str
    status: str
    conclusion: str | None
    updated_at: str
    html_url: str


class Job(TypedDict):
    name: str
    conclusion: str | None


def assess(run: Run | None, jobs: list[Job], shards: int, same_harness: bool, now: datetime) -> tuple[str, bool]:
    if run is None:
        return "No scheduled full examples run exists.", False
    lines = [f"Full baseline: {run['html_url']}", f"SDK revision: `{run['head_sha']}`"]
    if run["head_branch"] != "main" or run["event"] != "schedule":
        return "The candidate is not a scheduled main run.", False
    age = (now - datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))).total_seconds()
    expected = {"registered-examples / checks", "example-tests"} | {
        f"registered-examples / live ({index}/{shards})" for index in range(1, shards + 1)
    }
    succeeded = {job["name"] for job in jobs if job["conclusion"] == "success"}
    missing = expected - succeeded
    complete = (
        run["status"] == "completed"
        and run["conclusion"] == "success"
        and 0 <= age <= 24 * 60 * 60
        and same_harness
        and not missing
    )
    lines += [
        f"Run result: {run['status']} / {run['conclusion'] or 'pending'}",
        f"Age: {age / 3600:.1f} hours (maximum 24 hours)",
        f"Current harness: {'yes' if same_harness else 'no'}",
        f"Expected integration shards: {shards}",
        f"Coverage: {'complete' if complete else 'incomplete, failed or stale'}",
    ]
    if missing:
        lines += ["", "Expected jobs without success:", *[f"- {name}" for name in sorted(missing)]]
    lines += [
        "",
        "This records full workflow coverage at the SDK revision above, not proof that every later main commit was fully tested.",
    ]
    return "\n\n".join(lines) + "\n", complete


def api(path: str) -> str:
    return subprocess.check_output(["gh", "api", path], text=True)


def main() -> None:
    repository = os.environ["GITHUB_REPOSITORY"]
    runs = cast(
        dict[str, list[Run]],
        json.loads(
            api(f"repos/{repository}/actions/workflows/nightly-examples.yml/runs?branch=main&event=schedule&per_page=1")
        ),
    )["workflow_runs"]
    run = runs[0] if runs else None
    jobs: list[Job] = []
    same_harness = False
    if run is not None:
        pages = json.loads(
            subprocess.check_output(
                [
                    "gh",
                    "api",
                    "--paginate",
                    "--slurp",
                    f"repos/{repository}/actions/runs/{run['id']}/jobs?filter=latest&per_page=100",
                ],
                text=True,
            )
        )
        jobs = cast(list[Job], [job for page in pages for job in page["jobs"]])
        same_harness = True
        for path in (
            ".github/workflows/nightly-examples.yml",
            ".github/workflows/paired-sdk-examples.yml",
            "scripts/ci_integration_examples.py",
            "scripts/integration_examples.json",
            "tests/run_examples.sh",
        ):
            current = json.loads(api(f"repos/{repository}/contents/{path}?ref=main"))["sha"]
            tested = json.loads(api(f"repos/{repository}/contents/{path}?ref={run['head_sha']}"))["sha"]
            same_harness &= current == tested
    registry = json.loads(Path("scripts/integration_examples.json").read_text())
    summary, complete = assess(run, jobs, max(2, (len(registry) + 1) // 2), same_harness, datetime.now(timezone.utc))
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as output:
        _ = output.write("## Full baseline freshness\n\n" + summary)
    print(summary)
    if not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
