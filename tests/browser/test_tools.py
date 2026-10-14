import pytest
from notte_browser.errors import NoToolProvidedError
from notte_browser.tools.base import EmailReadAction

import notte


@pytest.fixture
def action():
    return EmailReadAction(only_unread=False, timedelta=None)


def test_tool_execution_should_fail_if_no_tool_provided_in_session(action: EmailReadAction):
    with notte.Session(headless=True) as session:
        with pytest.raises(NoToolProvidedError):
            _ = session.execute(action=action)
