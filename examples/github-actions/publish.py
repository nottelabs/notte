"""Opt-in GitHub REST publication. Never merges or edits executable source."""

import base64
import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from proposal import MAP_PATH, apply_proposal


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args):
        return None


def publish(
    source: bytes,
    proposal: bytes,
    digest: str,
    *,
    repository: str,
    base: str,
    source_sha: str,
    run_id: str,
    token: str,
    api_url: str = "https://api.github.com",
) -> str | None:
    updated = apply_proposal(source, proposal, digest)
    if updated == source:
        return None
    if not re.fullmatch(r"[a-zA-Z0-9-]+/[a-zA-Z0-9_.-]+", repository) or repository.split("/")[1] in {".", ".."}:
        raise ValueError("Invalid repository")
    if base != "main" or not re.fullmatch(r"[a-f0-9]{40}", source_sha) or not re.fullmatch(r"[0-9]+", run_id):
        raise ValueError("Publication requires a trusted main commit and workflow run ID")
    if not token:
        raise ValueError("Set the GitHub token only for the opt-in publish job")
    prefix = f"/repos/{repository}"
    branch = f"notte-selector-repair-{run_id}"
    opener = build_opener(NoRedirect())

    def request(method, path, data=None, *, missing=False):
        body = json.dumps(data).encode() if data is not None else None
        req = Request(
            api_url.rstrip("/") + prefix + path,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2026-03-10",
                "Content-Type": "application/json",
                "User-Agent": "notte-selector-repair-example",
            },
        )
        try:
            with opener.open(req, timeout=20) as response:
                return json.load(response)
        except HTTPError as error:
            error.close()
            if missing and error.code == 404:
                return None
            raise RuntimeError(f"GitHub HTTP {error.code}") from None
        except Exception:
            raise RuntimeError("GitHub request failed") from None

    def contents(ref):
        row = request("GET", f"/contents/{MAP_PATH}?{urlencode({'ref': ref})}")
        if row.get("type") != "file" or row.get("encoding") != "base64":
            raise RuntimeError("Expected the fixed selector-map file")
        return row, base64.b64decode(row["content"])

    head = request("GET", "/git/ref/heads/main")
    if head["object"]["sha"] != source_sha:
        raise RuntimeError("Main advanced after validation; run the workflow again")
    original, remote = contents(source_sha)
    if remote != source:
        raise RuntimeError("Checked-out selector map does not match the validated commit")
    existing = request("GET", f"/git/ref/heads/{branch}", missing=True)
    if existing is None:
        request("POST", "/git/refs", {"ref": f"refs/heads/{branch}", "sha": source_sha})
        current, current_bytes = original, source
    else:
        current, current_bytes = contents(branch)
        if current_bytes not in {source, updated}:
            raise RuntimeError("Repair branch contains other changes; review it manually")
        if existing["object"]["sha"] != source_sha:
            comparison = request("GET", f"/compare/{source_sha}...{branch}")
            if (
                comparison.get("ahead_by") != 1
                or comparison.get("behind_by") != 0
                or [item["filename"] for item in comparison.get("files", [])] != [MAP_PATH]
                or len(comparison.get("commits", [])) != 1
                or [parent["sha"] for parent in comparison["commits"][0].get("parents", [])] != [source_sha]
            ):
                raise RuntimeError("Repair branch contains unrelated commits or files")
    if current_bytes != updated:
        if existing is not None and existing["object"]["sha"] != source_sha:
            raise RuntimeError("Repair branch advanced; review it manually")
        request(
            "PUT",
            f"/contents/{MAP_PATH}",
            {
                "message": "Update validated browser selectors",
                "branch": branch,
                "sha": current["sha"],
                "content": base64.b64encode(updated).decode(),
            },
        )
    query = urlencode({"state": "open", "base": base, "head": f"{repository.split('/')[0]}:{branch}"})
    pulls = request("GET", f"/pulls?{query}")
    if len(pulls) > 1:
        raise RuntimeError("Multiple matching pull requests require manual review")
    if pulls:
        return pulls[0]["html_url"]
    result = request(
        "POST",
        "/pulls",
        {
            "title": "Repair browser selectors",
            "head": branch,
            "base": base,
            "draft": True,
            "body": "Update the selector map after live DOM validation. Review the proposed selectors before merging.",
        },
    )
    return result["html_url"]


if __name__ == "__main__":
    try:
        path = Path(MAP_PATH)
        if path.is_symlink():
            raise ValueError("Selector map must be a regular file")
        url = publish(
            path.read_bytes(),
            Path("selector-proposal/proposal.json").read_bytes(),
            os.environ["PROPOSAL_SHA256"],
            repository=os.environ["GITHUB_REPOSITORY"],
            base="main",
            source_sha=os.environ["GITHUB_SHA"],
            run_id=os.environ["GITHUB_RUN_ID"],
            token=os.environ["GH_TOKEN"],
        )
        print(url or "No selector changes")
    except Exception:
        raise SystemExit("Selector proposal publication failed; no automatic merge is performed") from None
