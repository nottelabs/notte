from dotenv import load_dotenv
from notte_sdk import NotteClient


def test_simple_listing():
    _ = load_dotenv()
    notte = NotteClient()

    # Default listing
    sessions = notte.sessions.list()
    assert isinstance(sessions, list)

    # With pagination
    sessions = notte.sessions.list(page=2, page_size=5)
    assert isinstance(sessions, list)

    # With filters
    sessions = notte.sessions.list(only_active=False)
    assert isinstance(sessions, list)
