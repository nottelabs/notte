"""Complete only exact bot-produced heads, using trusted default-branch code."""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import zipfile
from typing import NotRequired, TypedDict, cast

REPOSITORY = "nottelabs/notte"
BOT = "andreakiro"
GREPTILE_APP_ID = 867647
GREPTILE_BOT_ID = 165735046
# Fixed branches opened by scheduled or dispatched runs on main.
PRODUCERS = {
    "chore/bump-submodules": ".github/workflows/bump-submodules.yml",
    "chore/refresh-llms": ".github/workflows/refresh-llms.yml",
    "chore/bump-openapi": ".github/workflows/openapi-bump.yml",
}
# One branch per release, opened by the release run of that tag.
RELEASE_PRODUCER = ".github/workflows/pypi-release.yml"
# Regenerates an owned release branch on main once main has moved past it.
RELEASE_REFRESHER = ".github/workflows/update-bot-pr.yml"
RELEASE_BRANCH = re.compile(r"chore/python-version-after-(v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))")


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


class Producer(TypedDict):
    path: str
    events: set[str]
    ref: str


def producers(branch: str) -> list[Producer]:
    """The workflows, events and run refs allowed to produce this branch."""
    if branch in PRODUCERS:
        return [{"path": PRODUCERS[branch], "events": {"schedule", "workflow_dispatch"}, "ref": "main"}]
    release = RELEASE_BRANCH.fullmatch(branch)
    if release is not None:
        return [
            {"path": RELEASE_PRODUCER, "events": {"push"}, "ref": release.group(1)},
            {"path": RELEASE_REFRESHER, "events": {"push", "schedule", "workflow_dispatch"}, "ref": "main"},
        ]
    return []


def gh(*args: str) -> bytes:
    return subprocess.check_output(["gh", *args], timeout=45)


def api(path: str):
    return json.loads(gh("api", path))


def reviewer_permission(login: str) -> str:
    try:
        response = gh("api", "--include", f"repos/{REPOSITORY}/collaborators/{login}/permission")
    except subprocess.CalledProcessError as error:
        # Only this permission lookup may treat an HTTP 404 as unauthorized.
        # Other request failures and unparseable status output remain errors.
        if isinstance(error.output, bytes):
            status = error.output.splitlines()[0] if error.output else b""
            if re.fullmatch(rb"HTTP/[0-9.]+ 404(?: [^\r\n]*)?", status):
                return "none"
        raise
    headers, body = response.replace(b"\r\n", b"\n").split(b"\n\n", 1)
    if not re.fullmatch(rb"HTTP/[0-9.]+ 200(?: [^\r\n]*)?", headers.splitlines()[0]):
        raise ValueError("Invalid reviewer permission response status")
    permission = json.loads(body)["permission"]
    if not isinstance(permission, str) or permission not in {"none", "read", "triage", "write", "maintain", "admin"}:
        raise ValueError("Invalid reviewer permission response")
    return permission


def owned(pr: Pull) -> bool:
    return (
        pr["state"] == "open"
        and not pr["draft"]
        and pr["user"]["login"] == BOT
        and pr["base"]["ref"] == "main"
        and pr["base"]["repo"]["full_name"] == REPOSITORY
        and pr["head"]["repo"] is not None
        and pr["head"]["repo"]["full_name"] == REPOSITORY
        and bool(producers(pr["head"]["ref"]))
        and re.fullmatch(r"[0-9a-f]{40}", pr["head"]["sha"]) is not None
    )


def attested(pr: Pull) -> bool:
    markers = re.findall(r"<!-- bot-pr-run: ([0-9]+) -->", pr["body"] or "")
    if len(markers) != 1:
        return False
    run_id = markers[0]
    expected = producers(pr["head"]["ref"])
    if not expected:
        return False
    run = api(f"repos/{REPOSITORY}/actions/runs/{run_id}")
    if not (
        run["repository"]["full_name"] == REPOSITORY
        and run["head_repository"]["full_name"] == REPOSITORY
        and any(
            run["head_branch"] == item["ref"] and run["event"] in item["events"] and run["path"] == item["path"]
            for item in expected
        )
        and run["status"] == "completed"
        and run["conclusion"] == "success"
    ):
        return False
    # The producer's workflow and code must have come from reviewed main history
    # (a release tag must point at a main commit).
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
            if reviewer_permission(login) in {"write", "maintain", "admin"}:
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


def release_pulls() -> list[int]:
    pages = json.loads(
        gh("api", "--paginate", "--slurp", f"repos/{REPOSITORY}/pulls?state=open&base=main&per_page=100")
    )
    return [
        pull["number"]
        for page in pages
        for pull in page
        if pull["head"]["repo"] is not None
        and pull["head"]["repo"]["full_name"] == REPOSITORY
        and RELEASE_BRANCH.fullmatch(pull["head"]["ref"]) is not None
    ]


def stale(number: int) -> Pull | None:
    """The PR, if its current head is the exact attested bot head and main has moved past it.

    A head with any commit the producing run did not push (a person's push, or
    GitHub's "Update branch") is not attested, so it stays with a person.
    """
    pr = cast(Pull, api(f"repos/{REPOSITORY}/pulls/{number}"))
    if not owned(pr) or not attested(pr):
        return None
    comparison = api(f"repos/{REPOSITORY}/compare/main...{pr['head']['sha']}")
    return pr if comparison["behind_by"] > 0 else None


def find_stale() -> dict[str, str]:
    """The refresh PR and one release PR (at most) that update-bot-pr regenerates on main."""
    found = {"openapi": "", "release_number": "", "release_branch": "", "release_tag": "", "release_head": ""}
    branch = "chore/bump-openapi"
    pulls = api(f"repos/{REPOSITORY}/pulls?state=open&base=main&head=nottelabs:{branch}&per_page=100")
    if len(pulls) == 1 and stale(pulls[0]["number"]) is not None:
        found["openapi"] = str(pulls[0]["number"])
    # One per run: a run uploads a single bot-pr artifact. Later runs take the next one.
    for number in sorted(release_pulls()):
        pr = stale(number)
        if pr is None:
            continue
        release = RELEASE_BRANCH.fullmatch(pr["head"]["ref"])
        if release is None:
            continue
        found.update(
            release_number=str(number),
            release_branch=pr["head"]["ref"],
            release_tag=release.group(1),
            release_head=pr["head"]["sha"],
        )
        break
    return found


def main() -> int:
    if os.environ["GITHUB_REPOSITORY"] != REPOSITORY or api("user")["login"] != BOT:
        raise RuntimeError("Unexpected bot repository or authorization")
    if sys.argv[1:] == ["--stale"]:
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            for key, value in find_stale().items():
                print(f"{key}={value}", file=output)
        return 0
    failed = False

    def attempt(label: str, number: int) -> None:
        nonlocal failed
        try:
            print(f"PR #{number}: {'merged' if complete(number) else 'left open'}")
        except Exception as error:
            failed = True
            print(f"{label}: {type(error).__name__}: {error}", file=sys.stderr)

    for branch in PRODUCERS:
        try:
            pulls = api(f"repos/{REPOSITORY}/pulls?state=open&base=main&head=nottelabs:{branch}&per_page=100")
        except Exception as error:
            failed = True
            print(f"{branch}: {type(error).__name__}: {error}", file=sys.stderr)
            continue
        if len(pulls) == 1:
            attempt(branch, pulls[0]["number"])
    try:
        numbers = release_pulls()
    except Exception as error:
        failed = True
        print(f"{RELEASE_BRANCH.pattern}: {type(error).__name__}: {error}", file=sys.stderr)
        numbers = []
    for number in numbers:
        attempt(RELEASE_BRANCH.pattern, number)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
