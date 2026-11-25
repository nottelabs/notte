# @sniptest filename=onepassword_autofill.py
# @sniptest typecheck_only=true
import os
import time

import httpx

api = httpx.Client(
    base_url="https://api.notte.cc",
    headers={"Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}"},
    timeout=90,
)

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
    # Send the link to the person who approves in 1Password. Never give it to a model.
    print("Approve in 1Password:", request["app_link"])

    # 3. Wait for the decision
    while request["state"] == "pending":
        time.sleep(5)
        request = (
            api.get(f"/sessions/{session_id}/onepassword/access-requests/{request['id']}").raise_for_status().json()
        )
    if request["state"] != "resolved" or not request["grants"]:
        raise RuntimeError(f"Access was not granted: {request['state']}")
    grant_id = request["grants"][0]["id"]

    # 4. 1Password fills and submits the login form
    fill = (
        api.post(
            f"/sessions/{session_id}/onepassword/fill",
            json={"grant_id": grant_id, "url": "https://github.com/login"},
        )
        .raise_for_status()
        .json()
    )
    # `fill_submitted` means the form was sent. The page URL shows whether the site accepted it.
    print(fill["status"], fill["url"])

    # 5. Release the session to your code
    _ = api.post(f"/sessions/{session_id}/onepassword/release").raise_for_status()
except BaseException:
    _ = api.delete(f"/sessions/{session_id}/stop")
    raise

# Signed in: connect to the session as you would to any other
signed_in_session = session_id
