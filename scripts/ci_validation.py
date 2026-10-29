"""Separate automatic offline feedback from deliberate, exact-head live validation."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import TypeAlias, TypedDict, cast

from scripts.ci_scope import ALL, GROUPS

Scope: TypeAlias = dict[str, bool | str | list[str] | list[dict[str, str]]]
LIVE = {"python_live", "llm_provider_live", "node_live", "docs_live", "paired_live", "readme_live"}


class Need(TypedDict):
    result: str
    outputs: dict[str, str]


class Creator(TypedDict):
    login: str


class Status(TypedDict):
    context: str
    state: str
    url: str
    target_url: str | None
    creator: Creator


def authorized(statuses: list[Status], repository: str, head: str, run_id: str, actor: str) -> bool:
    """Only a writer-created status for this head/run and rerunning actor authorizes live work."""
    if not re.fullmatch(r"[0-9a-f]{40}", head) or not run_id.isdecimal() or not actor:
        raise ValueError("Invalid live-validation identity")
    context = f"ci/live-validation/{run_id}"
    for status in statuses:  # GitHub returns newest first; a revocation supersedes older success.
        if status["context"].lower() == context:
            return (
                status["state"] == "success"
                and status["url"] == f"https://api.github.com/repos/{repository}/statuses/{head}"
                and status["target_url"] == f"https://github.com/{repository}/actions/runs/{run_id}"
                and status["creator"]["login"].lower() == actor.lower()
                and not actor.lower().endswith("[bot]")
            )
    return False


def plan(
    scope: Scope, event: str, attempt: int, trusted: bool = True, live_authorized: bool = False
) -> tuple[Scope, bool]:
    if attempt < 1 or any(not isinstance(scope.get(flag), bool) for flag in ALL):
        raise ValueError("Incomplete CI selection or invalid run attempt")
    deferred = (
        event == "pull_request" and not (trusted and live_authorized) and any(scope[flag] is True for flag in LIVE)
    )
    execution = dict(scope)
    if deferred:
        execution.update({flag: False for flag in LIVE})
    return execution, deferred


def assess(needs: dict[str, Need]) -> tuple[str, bool]:
    changes = needs.get("changes")
    if changes is None or changes["result"] != "success":
        return "Suite selection failed; validation is incomplete.", False
    outputs = changes["outputs"]
    selected = cast(Scope, json.loads(outputs["selected_scope"]))
    execution = cast(Scope, json.loads(outputs["scope"]))
    if any(not isinstance(selected.get(flag), bool) or not isinstance(execution.get(flag), bool) for flag in ALL):
        raise ValueError("Incomplete CI selection")
    deferred = outputs["live_deferred"]
    if deferred not in {"true", "false"}:
        raise ValueError("Invalid live-validation state")
    expected = dict(selected)
    if deferred == "true":
        expected.update({flag: False for flag in LIVE})
    if execution != expected:
        return "Selected coverage was removed; validation is incomplete.", False
    failures = [
        family
        for family, flags in GROUPS.items()
        if (any(execution[flag] is True for flag in flags) or (family == "python" and execution.get("file_checks")))
        and (family not in needs or needs[family]["result"] != "success")
    ]
    failures += [name for name, job in needs.items() if job["result"] in {"failure", "cancelled"}]
    if failures:
        return "Failed or missing selected suites: " + ", ".join(sorted(set(failures))), False
    if deferred == "true":
        return (
            "Offline feedback only. Authorize this run and head, then use Re-run all jobs for live validation.",
            False,
        )
    return "All selected checks passed for this head.", True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("phase", choices=("plan", "gate"))
    args = parser.parse_args()
    if args.phase == "plan":
        scope = cast(Scope, json.loads(os.environ["SCOPE"]))
        trusted = os.environ["TRUSTED_LIVE"]
        if trusted not in {"true", "false"}:
            raise ValueError("Invalid live authorization")
        event = os.environ["EVENT_NAME"]
        live_authorized = False
        if event == "pull_request" and trusted == "true":
            pages = cast(list[list[Status]], json.loads(Path(os.environ["AUTHORIZATION_STATUSES"]).read_text()))
            live_authorized = authorized(
                [status for page in pages for status in page],
                os.environ["GITHUB_REPOSITORY"],
                os.environ["HEAD_SHA"],
                os.environ["GITHUB_RUN_ID"],
                os.environ["TRIGGERING_ACTOR"],
            )
        execution, deferred = plan(scope, event, int(os.environ["RUN_ATTEMPT"]), trusted == "true", live_authorized)
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            _ = output.write("scope=" + json.dumps(execution, separators=(",", ":")) + "\n")
            _ = output.write("live_deferred=" + str(deferred).lower() + "\n")
            _ = output.write("live_authorized=" + str(live_authorized).lower() + "\n")
        message = (
            "Offline checks run on this push. Before merging, a maintainer must authorize this exact run/head "
            + "and use **Re-run all jobs** to execute selected live checks. A new push requires new authorization. "
            + "A rerun alone never authorizes live coverage."
            if deferred
            else "This run executes all selected coverage."
        )
        if deferred and trusted == "false":
            message = "Fork live coverage requires a reviewed same-repository branch; no secrets are provided here."
        elif deferred:
            repository, head, run_id = (os.environ[name] for name in ("GITHUB_REPOSITORY", "HEAD_SHA", "GITHUB_RUN_ID"))
            message += (
                "\n\nA human maintainer can run these commands with the same GitHub account:\n\n```sh\n"
                + f"gh api --method POST repos/{repository}/statuses/{head} -f state=success "
                + f"-f context=ci/live-validation/{run_id} "
                + f"-f target_url=https://github.com/{repository}/actions/runs/{run_id}\n"
                + f"gh run rerun {run_id} --repo {repository}\n```\n"
            )
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as summary:
            _ = summary.write("## CI validation\n\n" + message + "\n")
        print(message)
        return
    message, complete = assess(cast(dict[str, Need], json.loads(os.environ["RESULTS"])))
    print(message)
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as summary:
        _ = summary.write("## Merge validation\n\n" + message + "\n")
    if not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
