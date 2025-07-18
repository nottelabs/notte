import pytest
from notte_browser.errors import NoToolProvidedError
from notte_browser.tools.base import EmailReadAction, PersonaTool
from notte_sdk import NotteClient
from notte_sdk.endpoints.personas import Persona

import notte

client = NotteClient()


@pytest.fixture
def persona():
    return client.Persona("7abb4f37-25a1-4409-98d9-c4c916918254")


@pytest.fixture
def action():
    return EmailReadAction(only_unread=False, timedelta=None)


def test_persona_tool(persona: Persona, action: EmailReadAction):
    tool: PersonaTool = PersonaTool(persona)

    res = tool.execute(action)
    assert res.success
    assert "Successfully read" in res.message
    assert res.data is not None
    assert res.data.structured is not None
    assert len(res.data.structured.get().emails) > 0


def test_tool_execution_should_fail_if_no_tool_provided_in_session(action: EmailReadAction):
    with notte.Session(headless=True) as session:
        with pytest.raises(NoToolProvidedError):
            _ = session.execute(action=action)


def test_tool_execution_in_session(persona: Persona, action: EmailReadAction):
    tool: PersonaTool = PersonaTool(persona)
    with notte.Session(headless=True, tools=[tool]) as session:
        out = session.execute(action=action)
        assert out.success
        assert "Successfully read" in out.message
        assert out.data is not None
        assert out.data.structured is not None
        assert len(out.data.structured.get().emails) > 0


def test_signup_email_extraction(persona: Persona):
    with notte.Session(headless=True) as session:
        agent = notte.Agent(session=session, persona=persona, max_steps=10)
        resp = agent.run(
            task=(
                "Go to console.notte.cc, login with the email signup email, verify the account. "
                "Stop after the account is verified, i.e as soon as your are on the 'One more second' page."
                "CRITICAL: do not fill the in the onboarding form, just stop after the account is verified"
            ),
            url="https://console.notte.cc",
        )
        assert resp.success, f"Failed to run agent: {resp.answer}"
