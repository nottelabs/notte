"""Require every selected suite, live suites included, to pass on the current head before merging."""

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


def assess(needs: dict[str, Need], trusted: bool = True) -> tuple[str, bool]:
    """`trusted` is false for fork PRs, whose live jobs skip because they receive no secrets."""
    changes = needs.get("changes")
    if changes is None or changes["result"] != "success":
        return "Suite selection failed; validation is incomplete.", False
    scope = cast(Scope, json.loads(changes["outputs"]["scope"]))
    if any(not isinstance(scope.get(flag), bool) for flag in ALL):
        raise ValueError("Incomplete CI selection")
    failures = [
        family
        for family, flags in GROUPS.items()
        if (any(scope[flag] is True for flag in flags) or (family == "python" and scope.get("file_checks")))
        and (family not in needs or needs[family]["result"] != "success")
    ]
    failures += [name for name, job in needs.items() if job["result"] in {"failure", "cancelled"}]
    if failures:
        return "Failed or missing selected suites: " + ", ".join(sorted(set(failures))), False
    if not trusted and any(scope[flag] is True for flag in LIVE):
        return "Fork live coverage requires a reviewed same-repository branch; no secrets are provided here.", False
    return "All selected checks passed for this head.", True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("phase", choices=("gate",))
    _ = parser.parse_args()
    trusted = os.environ["TRUSTED_LIVE"]
    if trusted not in {"true", "false"}:
        raise ValueError("Invalid live trust state")
    message, complete = assess(cast(dict[str, Need], json.loads(os.environ["RESULTS"])), trusted == "true")
    print(message)
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as summary:
        _ = summary.write("## Merge validation\n\n" + message + "\n")
    if not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
