# @sniptest filename=upload_cookies.py
from typing import Any

from notte_sdk import NotteClient

# Upload cookies for github.com to automatically login
cookies: list[dict[str, Any]] = [
    {
        "name": "sb-db-auth-token",
        "value": "base64-cookie-value",
        "domain": "github.com",
        "path": "/",
        "expires": 9778363203.913704,
        "httpOnly": False,
        "secure": False,
        "sameSite": "Lax",
    }
]
# create a new session
client = NotteClient()
with client.Session() as session:
    _ = session.set_cookies(cookies=cookies)  # type: ignore[arg-type]  # can also set cookie_file="path/to/cookies.json"

    # Use the cookies in your session
    agent = client.Agent(session=session, max_steps=5)
    res = agent.run(
        task="go to nottelabs/notte get repo info. Fail if you are not logged in",
        url="https://github.com/nottelabs/notte",
    )

    # or get the cookies from the session
    cookies_resp = session.get_cookies()
