"""Separate automatic offline feedback from deliberate, exact-head live validation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import TypeAlias, TypedDict, cast

from scripts.ci_scope import ALL, GROUPS

Scope: TypeAlias = dict[str, bool | str | list[str] | list[dict[str, str]]]
LIVE = {"python_live", "llm_provider_live", "node_live", "docs_live", "paired_live", "readme_live"}


class Need(TypedDict):
    result: str
    outputs: dict[str, str]


def plan(scope: Scope, event: str, attempt: int, trusted: bool = True) -> tuple[Scope, bool]:
    if attempt < 1 or any(not isinstance(scope.get(flag), bool) for flag in ALL):
        raise ValueError("Incomplete CI selection or invalid run attempt")
    deferred = event == "pull_request" and (attempt == 1 or not trusted) and any(scope[flag] is True for flag in LIVE)
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
        return "Offline feedback only. Live validation is required: use Re-run all jobs on this run.", False
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
        execution, deferred = plan(scope, os.environ["EVENT_NAME"], int(os.environ["RUN_ATTEMPT"]), trusted == "true")
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            _ = output.write("scope=" + json.dumps(execution, separators=(",", ":")) + "\n")
            _ = output.write("live_deferred=" + str(deferred).lower() + "\n")
        message = (
            "Offline checks run on this push. Before merging, use **Re-run all jobs** on this exact run "
            + "to execute all selected live checks. A new push requires new live validation. "
            + "Re-running only failed jobs or the gate does not authorize deferred coverage."
            if deferred
            else "This run executes all selected coverage."
        )
        if deferred and trusted == "false":
            message = "Fork live coverage requires a reviewed same-repository branch; no secrets are provided here."
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
