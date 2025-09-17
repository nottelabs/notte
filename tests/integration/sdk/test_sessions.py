import pytest
from dotenv import load_dotenv
from notte_core.common.config import BrowserType
from notte_sdk import NotteClient

_ = load_dotenv()


def test_start_close_session():
    client = NotteClient()

    response = client.sessions.start()
    assert response.status == "active"
    response = client.sessions.stop(session_id=response.session_id)
    assert response.status == "closed"


def test_start_close_session_factory():
    client = NotteClient()
    with client.Session(proxies=False) as session:
        assert session.session_id is not None
        status = session.status()
        assert status.status == "active"
    assert session.response is not None
    assert session.response.status == "closed"


def test_start_close_session_with_proxy():
    client = NotteClient()
    with client.Session(proxies=True) as session:
        assert session.session_id is not None
        status = session.status()
        assert status.status == "active"
    assert session.response is not None


def test_start_close_session_with_viewport():
    client = NotteClient()
    with client.Session(viewport_height=100, viewport_width=100) as session:
        assert session.session_id is not None
        status = session.status()
        assert status.status == "active"
    assert session.response is not None


@pytest.fixture
def session_id() -> str:
    return "ebebbee8-213e-46f2-b9d1-0f4dc5545a6a"


def test_replay_session(session_id: str):
    client = NotteClient()
    response = client.sessions.replay(session_id=session_id)
    assert len(response.replay) > 0


@pytest.mark.parametrize("browser_type", ["chrome", "firefox", "chromium"])
def test_start_close_session_with_browser_type(browser_type: BrowserType):
    client = NotteClient()
    with client.Session(headless=True, browser_type=browser_type) as session:
        assert session.session_id is not None
        status = session.status()
        assert status.status == "active"
    assert session.response is not None
