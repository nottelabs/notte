import pytest
from notte_browser.tools.base import EmailReadAction, PersonaTool
from notte_sdk import NotteClient
from notte_sdk.endpoints.personas import Persona

import notte

client = NotteClient()


@pytest.fixture
def persona():
    return client.Persona("f2e2834b-a054-4a96-a388-a447c37756ff")


def test_persona_tool(persona: Persona):
    tool: PersonaTool = PersonaTool(persona)

    res = tool.execute(EmailReadAction(only_unread=False))
    assert res.success
    assert "Successfully read" in res.message
    assert res.data is not None
    assert res.data.structured is not None
    assert len(res.data.structured.get().emails) > 0


def test_tool_execution_should_fail_if_no_tool_provided_in_session(persona: Persona):
    with notte.Session(headless=True) as session:
        with pytest.raises(ValueError):
            _ = session.step(action=EmailReadAction(only_unread=False))


def test_tool_execution_in_session(persona: Persona):
    tool: PersonaTool = PersonaTool(persona)
    with notte.Session(headless=True, tools=[tool]) as session:
        out = session.step(action=EmailReadAction(only_unread=False))
        assert out.success
        assert "Successfully read" in out.message
        assert out.data is not None
        assert out.data.structured is not None
        assert len(out.data.structured.get().emails) > 0
