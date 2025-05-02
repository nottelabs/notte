import json
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from notte_sdk import NotteClient
from notte_sdk.types import Cookie
from pytest import fixture


@fixture
def cookies() -> list[Cookie]:
    return [
        Cookie.model_validate(
            {
                "name": "sb-db-auth-token",
                "value": "base64-XFV",
                "domain": "console.notte.cc",
                "path": "/",
                "expires": 778363203.913704,
                "httpOnly": False,
                "secure": False,
                "sameSite": "Lax",
            }
        )
    ]


def test_upload_cookies(cookies: list[Cookie]):
    _ = load_dotenv()
    notte = NotteClient()

    with tempfile.TemporaryDirectory() as temp_dir:
        cookie_path = Path(temp_dir) / "cookies.json"
        with open(cookie_path, "w") as f:
            json.dump([cookie.model_dump() for cookie in cookies], f)

        # create a new session
        with notte.Session() as session:
            _ = session.upload_cookies(cookie_file=str(cookie_path))

            # Use the cookies in your session
            _ = notte.agents.run(
                task="go to console.notte.cc and check that you are logged in",
                url="https://console.notte.cc",
                session_id=session.session_id,
            )
