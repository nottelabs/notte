# @sniptest filename=onepassword_autofill.py
# @sniptest typecheck_only=true
# Run this yourself, in your own terminal, on the machine where 1Password runs.
# Never run it through an agent: the approval link must stay out of a model's context.
import os
import time
import webbrowser
from urllib.parse import urlsplit

import httpx

api = httpx.Client(
    base_url="https://api.notte.cc",
    headers={"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"},
    timeout=90,
)


def is_login_step(url: str) -> bool:
    # GitHub's sign-in form and the page it shows after a refused login. Adapt to your site.
    return urlsplit(url).path in {"/login", "/session"}


# 1. Start a session with 1Password. It stays `authenticating` until you release it.
session_id = api.post("/sessions/start", json={"onepassword": True}).raise_for_status().json()["session_id"]
try:
    # 2. Ask for access to one login
    request = (
        api.post(
            f"/sessions/{session_id}/onepassword/access-requests",
            json={
                "goal": "Sign in to GitHub to review open pull requests",
                "entries": [{"website": "https://github.com", "reason": "Review pull requests"}],
            },
        )
        .raise_for_status()
        .json()
    )
    # Open the approval link in your browser, without printing it.
    # From an agent, send it to the person through a channel the model cannot read instead.
    if request["app_link"] and not webbrowser.open(request["app_link"]):
        raise RuntimeError("Could not open a browser for the approval link")

    # 3. Wait for the decision
    while request["state"] == "pending":
        time.sleep(5)
        request = (
            api.get(f"/sessions/{session_id}/onepassword/access-requests/{request['id']}").raise_for_status().json()
        )
    if request["state"] != "resolved" or not request["grants"]:
        raise RuntimeError(f"Access was not granted: {request['state']}")
    grant_id = request["grants"][0]["id"]

    # 4. 1Password fills and submits the login form, one page per call
    body: dict[str, str] = {"grant_id": grant_id, "url": "https://github.com/login"}
    page_url = ""
    for _attempt in range(3):
        fill = api.post(f"/sessions/{session_id}/onepassword/fill", json=body).raise_for_status().json()
        # `fill_submitted` means the form was sent, not that the site accepted it
        if fill["status"] != "fill_submitted":
            raise RuntimeError(f"1Password did not submit the form: {fill['status']}")
        page_url = fill["url"]
        if not is_login_step(page_url):
            break
        # Still on a login page: fill the current page again
        body = {"grant_id": grant_id}
    if is_login_step(page_url):
        raise RuntimeError(f"Sign-in did not finish, still at {page_url}")

    # 5. Release the session to your code. Fills stop for good after this.
    _ = api.post(f"/sessions/{session_id}/onepassword/release").raise_for_status()
except BaseException:
    try:
        _ = api.delete(f"/sessions/{session_id}/stop")
    except httpx.HTTPError:
        pass  # keep the original error
    raise

# Released: connect to the session as you would to any other, and check that you are signed in
released_session = session_id
