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

client = NotteClient()
with client.Session() as session:
    _ = session.set_cookies(cookies=cookies)  # type: ignore[arg-type]  # can also set cookie_file="path/to/cookies.json"
    session.execute(type="goto", url="https://github.com/nottelabs/notte")
