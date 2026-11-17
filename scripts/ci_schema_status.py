"""Request a contract check using only this public repository's commit statuses."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, cast, final

CONTEXT = "SDK schema round trip"


@final
class GitHub:
    def __init__(self, token: str):
        self.token = token
        self.cached: dict[str, tuple[str, dict[str, Any]]] = {}

    def request(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"}
        if body is None and path in self.cached:
            headers["If-None-Match"] = self.cached[path][0]
        request = urllib.request.Request(
            f"https://api.github.com/{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                value = cast(dict[str, Any], json.load(response))
                if body is None and response.headers.get("ETag"):
                    self.cached[path] = (response.headers["ETag"], value)
                return value
        except urllib.error.HTTPError as error:
            if error.code == 304 and path in self.cached:
                return self.cached[path][1]
            raise RuntimeError(f"Public contract-status request failed (HTTP {error.code})") from None


def check(github: GitHub, repository: str, sha: str, actor_id: str, *, within: float = 1200) -> None:
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Expected the public repository and its exact SDK commit")
    if not re.fullmatch(r"[1-9][0-9]*", actor_id):
        raise ValueError("Configure SDK_SCHEMA_STATUS_ACTOR_ID with the trusted status publisher's public user ID")
    request_id = uuid.uuid4().hex
    description = f"request {request_id}"
    _ = github.request(
        f"repos/{repository}/statuses/{sha}",
        {
            "state": "pending",
            "context": CONTEXT,
            "description": description,
        },
    )
    print("Requested the SDK contract check. Waiting for its public result.", flush=True)
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        statuses = github.request(f"repos/{repository}/commits/{sha}/status")["statuses"]
        for status in statuses:
            if (
                status.get("context") == CONTEXT
                and str(status.get("creator", {}).get("id")) == actor_id
                and status.get("description", "").startswith(description + ": ")
            ):
                if status["state"] == "success":
                    print("The installed SDK contract matches its snapshot.")
                    return
                if status["state"] in {"failure", "error"}:
                    raise RuntimeError(
                        "The installed SDK contract check failed. Its owner must inspect the private diagnostics."
                    )
        time.sleep(min(10, max(0, deadline - time.monotonic())))
    raise TimeoutError("The SDK contract check did not publish a result before its deadline")


if __name__ == "__main__":
    check(
        GitHub(os.environ["GH_TOKEN"]),
        os.environ["GITHUB_REPOSITORY"],
        os.environ["SDK_SHA"],
        os.environ.get("SDK_SCHEMA_STATUS_ACTOR_ID", ""),
    )
