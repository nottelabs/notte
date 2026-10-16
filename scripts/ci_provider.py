"""Select an extraction provider from live GitHub metadata, without credentials."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

_SHA = re.compile(r"[0-9a-fA-F]{40}")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _repository(pr: dict[str, Any], side: str) -> str | None:
    branch = pr.get(side)
    if not isinstance(branch, dict) or "repo" not in branch:
        raise ValueError("Invalid PR branch metadata")
    repository = branch.get("repo")
    if repository is None:  # A deleted fork cannot authorize a paid run.
        return None
    if not isinstance(repository, dict) or not isinstance(repository.get("full_name"), str):
        raise ValueError("Invalid PR repository metadata")
    if not _REPOSITORY.fullmatch(repository["full_name"]):
        raise ValueError("Invalid PR repository identity")
    return repository["full_name"]


def _validate(pr: Any) -> dict[str, Any]:
    if not isinstance(pr, dict) or pr.get("state") not in ("open", "closed"):
        raise ValueError("Invalid PR metadata")
    _repository(pr, "base")
    _repository(pr, "head")
    if not isinstance(pr["base"].get("ref"), str) or not _is_sha(pr["head"].get("sha")):
        raise ValueError("Invalid PR branch metadata")
    user, labels = pr.get("user"), pr.get("labels")
    if not isinstance(user, dict) or not isinstance(user.get("login"), str) or not user["login"]:
        raise ValueError("Invalid PR author metadata")
    if not isinstance(labels, list) or any(
        not isinstance(label, dict) or not isinstance(label.get("name"), str) for label in labels
    ):
        raise ValueError("Invalid PR labels")
    return pr


def _same_repository(pr: dict[str, Any], repository: str) -> bool:
    return _repository(pr, "base") == repository and _repository(pr, "head") == repository


def _selected(pr: dict[str, Any]) -> bool:
    return pr["user"]["login"].lower() not in {"dependabot", "dependabot[bot]"} and any(
        label["name"] == "ci:openai" for label in pr["labels"]
    )


def select_provider(*, event: str, ref: str, repository: str, head: str, attempt: int, pulls: Any) -> dict[str, str]:
    """Labels select a provider; a PR's deliberate write-authorized rerun gates paid use."""
    if not _is_sha(head) or not _REPOSITORY.fullmatch(repository) or attempt < 1:
        raise ValueError("Invalid workflow identity")
    if not isinstance(pulls, list):
        raise ValueError("Expected a PR metadata array")
    result = {"provider": "gemini", "source_sha": head}
    if event != "pull_request" and not (event == "push" and ref == "refs/heads/main"):
        return result
    validated = [_validate(pr) for pr in pulls]
    if event == "pull_request":
        if not validated:  # The coordinator intentionally does not fetch fork PRs.
            return result
        if len(validated) != 1:
            raise ValueError("Ambiguous PR metadata")
        pr = validated[0]
        if not _same_repository(pr, repository):
            return result
        if pr["state"] != "open" or pr["base"]["ref"] != "main" or pr["head"]["sha"] != head:
            raise ValueError("PR metadata does not match this workflow head")
        if attempt > 1 and _selected(pr):
            result["provider"] = "openai"
        return result

    matches = []
    for pr in validated:
        merged, merge_sha = pr.get("merged"), pr.get("merge_commit_sha")
        if not isinstance(merged, bool) or (merge_sha is not None and not _is_sha(merge_sha)):
            raise ValueError("Invalid PR merge metadata")
        if (
            merged
            and pr["state"] == "closed"
            and _same_repository(pr, repository)
            and pr["base"]["ref"] == "main"
            and merge_sha == head
        ):
            matches.append(pr)
    if len(matches) > 1:
        raise ValueError("Ambiguous merged PR metadata")
    if matches and _selected(matches[0]):
        result["provider"] = "openai"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("event", "ref", "repository", "head"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--pulls", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = select_provider(
            event=args.event,
            ref=args.ref,
            repository=args.repository,
            head=args.head,
            attempt=args.attempt,
            pulls=json.loads(args.pulls.read_text(encoding="utf-8")),
        )
    except (OSError, ValueError, TypeError):
        parser.exit(2, "Invalid CI provider metadata\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
