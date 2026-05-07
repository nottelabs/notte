import pytest
from notte_browser.errors import NoToolProvidedError
from notte_browser.tools.base import EmailReadAction, PersonaTool
from notte_sdk import NotteClient
from notte_sdk.endpoints.personas import NottePersona

import notte

client = NotteClient()


@pytest.fixture
def persona():
    return client.Persona("131a21e1-8c8e-4016-80b9-765c0ce4fb5c")


@pytest.fixture
def action():
    return EmailReadAction(only_unread=False, timedelta=None)


@pytest.mark.asyncio
async def test_persona_tool(persona: NottePersona, action: EmailReadAction):
    tool: PersonaTool = PersonaTool(persona)

    res = await tool.aexecute(action)
    assert res.success
    if "no emails" in res.message.lower():
        return
    assert "Successfully read" in res.message
    assert res.data is not None
    assert res.data.structured is not None
    assert len(res.data.structured.get().emails) > 0


def test_tool_execution_should_fail_if_no_tool_provided_in_session(action: EmailReadAction):
    with notte.Session(headless=True) as session:
        with pytest.raises(NoToolProvidedError):
            _ = session.execute(action=action)


def test_tool_execution_in_session(persona: NottePersona, action: EmailReadAction):
    tool: PersonaTool = PersonaTool(persona)
    with notte.Session(headless=True, tools=[tool]) as session:
        out = session.execute(action=action)
        assert out.success
        if "no emails" in out.message.lower():
            return
        assert "Successfully read" in out.message
        assert out.data is not None
        assert out.data.structured is not None
        assert len(out.data.structured.get().emails) > 0


@pytest.mark.timeout(120)
@pytest.mark.flaky(reruns=3, reruns_delay=5)
def test_signup_email_extraction(persona: NottePersona):
    with notte.Session(headless=True) as session:
        agent = notte.Agent(session=session, persona=persona, max_steps=15)
        resp = agent.run(
            task=(
                "Go to console.notte.cc and authenticate with the persona's email. "
                "If the account does not exist yet, sign up; if it already exists, log in. Either path is fine. "
                "CRITICAL: never use Google sign-in, GitHub sign-in, or any other social/SSO option — "
                "always pick the plain email flow (email + password, or email magic link). "
                "When a verification or magic-link email is required, check the persona's inbox and open "
                "the link from that email to complete authentication. "
                "Success = you are authenticated and have landed inside the console (any logged-in page is "
                "acceptable, e.g. the 'One more second' interstitial, the personal/agent console, or the "
                "dashboard). Stop as soon as you reach any logged-in page. "
                "CRITICAL: do not fill in any onboarding form — stop immediately once authenticated."
            ),
            url="https://console.notte.cc",
        )
        assert resp.success, f"Failed to run agent: {resp.answer}"
