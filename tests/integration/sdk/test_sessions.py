import pytest
from notte_sdk import NotteClient


def test_start_close_session():
    client = NotteClient()

    response = client.sessions.start()
    assert response.status == "active"
    response = client.sessions.stop(session_id=response.session_id)
    assert response.status == "closed"


def test_start_close_session_factory():
    client = NotteClient()
    with client.Session(proxies=False, max_steps=1) as session:
        assert session.session_id is not None
        status = session.status()
        assert status.status == "active"
    assert session.response is not None
    assert session.response.status == "closed"


@pytest.fixture
def session_id() -> str:
    return "593103ec-76bb-4c31-a238-2b2859966704"


def test_replay_session(session_id: str):
    client = NotteClient()
    response = client.sessions.replay(session_id=session_id)
    assert len(response.replay) > 0
