"""Complete only exact bot-produced heads, using trusted default-branch code."""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import zipfile
from typing import NotRequired, TypedDict, cast

REPOSITORY = "nottelabs/notte"
BOT = "andreakiro"
GREPTILE_APP_ID = 867647
GREPTILE_BOT_ID = 165735046
PRODUCERS = {
    "chore/bump-submodules": ".github/workflows/bump-submodules.yml",
    "chore/refresh-llms": ".github/workflows/refresh-llms.yml",
}


class Repository(TypedDict):
    full_name: str


class User(TypedDict):
    login: str
    id: NotRequired[int]
    type: NotRequired[str]


class Base(TypedDict):
    ref: str
    repo: Repository


class Head(TypedDict):
    ref: str
    sha: str
    repo: Repository | None


class Pull(TypedDict):
    number: int
    state: str
    draft: bool
    body: str | None
    user: User
    base: Base
    head: Head


class Review(TypedDict):
    user: User
    state: str
    commit_id: str


def gh(*args: str) -> bytes:
    return subprocess.check_output(["gh", *args], timeout=45)


def api(path: str):
    return json.loads(gh("api", path))


def owned(pr: Pull) -> bool:
    return (
        pr["state"] == "open"
        and not pr["draft"]
        and pr["user"]["login"] == BOT
        and pr["base"]["ref"] == "main"
        and pr["base"]["repo"]["full_name"] == REPOSITORY
        and pr["head"]["repo"] is not None
        and pr["head"]["repo"]["full_name"] == REPOSITORY
        and pr["head"]["ref"] in PRODUCERS
        and re.fullmatch(r"[0-9a-f]{40}", pr["head"]["sha"]) is not None
    )


def attested(pr: Pull) -> bool:
    markers = re.findall(r"<!-- bot-pr-run: ([0-9]+) -->", pr["body"] or "")
    if len(markers) != 1:
        return False
    run_id = markers[0]
    run = api(f"repos/{REPOSITORY}/actions/runs/{run_id}")
    if not (
        run["repository"]["full_name"] == REPOSITORY
        and run["head_repository"]["full_name"] == REPOSITORY
        and run["head_branch"] == "main"
        and run["event"] in {"schedule", "workflow_dispatch"}
        and run["path"] == PRODUCERS[pr["head"]["ref"]]
        and run["status"] == "completed"
        and run["conclusion"] == "success"
    ):
        return False
    # The producer's workflow and code must have come from reviewed main history.
    comparison = api(f"repos/{REPOSITORY}/compare/{run['head_sha']}...main")
    if comparison["status"] not in {"ahead", "identical"}:
        return False
    artifacts = api(f"repos/{REPOSITORY}/actions/runs/{run_id}/artifacts")
    matches = [item for item in artifacts["artifacts"] if item["name"] == "bot-pr" and not item["expired"]]
    if len(matches) != 1 or matches[0]["size_in_bytes"] > 4096:
        return False
    archive = gh("api", f"repos/{REPOSITORY}/actions/artifacts/{matches[0]['id']}/zip")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        if zipped.namelist() != ["bot-pr.json"] or zipped.getinfo("bot-pr.json").file_size > 4096:
            return False
        manifest = json.loads(zipped.read("bot-pr.json"))
    return manifest == {
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_RUN_ID": run_id,
        "BRANCH": pr["head"]["ref"],
        "PR_NUMBER": str(pr["number"]),
        "HEAD_SHA": pr["head"]["sha"],
    }


def reviewed(pr: Pull) -> bool:
    reviews = json.loads(gh("api", "--paginate", "--slurp", f"repos/{REPOSITORY}/pulls/{pr['number']}/reviews"))
    latest: dict[str, Review] = {}
    for page in reviews:
        for review in page:
            if review["state"] in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
                latest[review["user"]["login"]] = review
    authorized: list[Review] = []
    for login, review in latest.items():
        if login in {pr["user"]["login"], BOT}:
            continue
        user = review["user"]
        if login == "greptile-apps[bot]" and user.get("id") == GREPTILE_BOT_ID and user.get("type") == "Bot":
            # These immutable GitHub identities bind the review to the trusted app,
            # even when GitHub reports its author association as NONE.
            app = api("apps/greptile-apps")
            if app["id"] == GREPTILE_APP_ID and app["slug"] == "greptile-apps":
                authorized.append(review)
        else:
            permission = api(f"repos/{REPOSITORY}/collaborators/{login}/permission")
            if permission["permission"] in {"write", "maintain", "admin"}:
                authorized.append(review)
    # A public read-only approval cannot update an older authorized approval.
    return not any(review["state"] == "CHANGES_REQUESTED" for review in authorized) and any(
        review["state"] == "APPROVED" and review["commit_id"] == pr["head"]["sha"] for review in authorized
    )


def checks_passed(pr: Pull) -> bool:
    # No waiting or retries. A later completion event reconciles pending checks.
    for required in (False, True):
        args = ["gh", "pr", "checks", str(pr["number"]), "--repo", REPOSITORY, "--json", "name,bucket"]
        if required:
            args.append("--required")
        result = subprocess.run(args, capture_output=True, timeout=45, check=False)
        if result.returncode in {1, 8}:  # Failed or pending checks leave the PR open.
            return False
        if result.returncode != 0:
            raise RuntimeError("Unable to read bot PR checks")
        checks = json.loads(result.stdout)
        if not checks or any(check["bucket"] not in {"pass", "skipping"} for check in checks):
            return False
        if required and not any(check["name"] == "tests" and check["bucket"] == "pass" for check in checks):
            return False
    return True


def complete(number: int) -> bool:
    path = f"repos/{REPOSITORY}/pulls/{number}"
    pr = cast(Pull, api(path))
    if not owned(pr) or not attested(pr) or not reviewed(pr) or not checks_passed(pr):
        return False
    # Revalidate ownership after reads, and let the merge API atomically enforce SHA.
    current = cast(Pull, api(path))
    if not owned(current) or current["head"]["sha"] != pr["head"]["sha"] or current["body"] != pr["body"]:
        return False
    # Keep the server's review, branch freshness and conversation rules in force.
    state = json.loads(
        gh("pr", "view", str(number), "--repo", REPOSITORY, "--json", "headRefOid,mergeStateStatus,reviewDecision")
    )
    if state != {"headRefOid": pr["head"]["sha"], "mergeStateStatus": "CLEAN", "reviewDecision": "APPROVED"}:
        return False
    _ = gh(
        "pr",
        "merge",
        str(number),
        "--repo",
        REPOSITORY,
        "--squash",
        "--match-head-commit",
        pr["head"]["sha"],
    )
    # Leave branch deletion to the repository, avoiding a race with tomorrow's push.
    return True


def main() -> None:
    if os.environ["GITHUB_REPOSITORY"] != REPOSITORY or api("user")["login"] != BOT:
        raise RuntimeError("Unexpected bot repository or authorization")
    for branch in PRODUCERS:
        pulls = api(f"repos/{REPOSITORY}/pulls?state=open&base=main&head=nottelabs:{branch}&per_page=100")
        if len(pulls) == 1:
            number = pulls[0]["number"]
            print(f"PR #{number}: {'merged' if complete(number) else 'left open'}")


if __name__ == "__main__":
    main()
