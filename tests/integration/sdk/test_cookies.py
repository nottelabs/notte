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
                "expires": 1904382506.913704,
                "httpOnly": False,
                "secure": False,
                "sameSite": "Lax",
            }
        )
    ]


def test_set_cookies(cookies: list[Cookie]):
    _ = load_dotenv()
    notte = NotteClient()

    with tempfile.TemporaryDirectory() as temp_dir:
        cookie_path = Path(temp_dir) / "cookies.json"
        with open(cookie_path, "w") as f:
            json.dump([cookie.model_dump() for cookie in cookies], f)

        # create a new session
        with notte.Session(timeout_minutes=1) as session:
            _ = session.set_cookies(cookie_file=str(cookie_path))


def test_get_cookies():
    _ = load_dotenv()
    notte = NotteClient()

    # create a new session
    with notte.Session(timeout_minutes=1) as session:
        _ = session.execute(type="goto", value="https://www.ecosia.org")
        _ = session.observe()
        resp = session.get_cookies()

    assert len(resp) > 0


def test_get_set_cookies(cookies: list[Cookie]):
    _ = load_dotenv()
    notte = NotteClient()

    with tempfile.TemporaryDirectory() as temp_dir:
        cookie_path = Path(temp_dir) / "cookies.json"
        with open(cookie_path, "w") as f:
            json.dump([cookie.model_dump() for cookie in cookies], f)

        # create a new session
        with notte.Session(timeout_minutes=1) as session:
            _ = session.set_cookies(cookie_file=str(cookie_path))

            resp = session.get_cookies()

        assert any(
            cookie.name == cookies[0].name and cookie.domain == cookies[0].domain and cookie.value == cookies[0].value
            for cookie in resp
        )
