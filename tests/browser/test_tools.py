import datetime as dt

import pytest
from notte_browser.errors import NoToolProvidedError
from notte_browser.tools.base import EmailReadAction, PersonaTool
from notte_sdk import NotteClient
from notte_sdk.endpoints.personas import NottePersona

import notte

client = NotteClient()

CONSOLE_SIGNIN_URL = "https://console.notte.cc/signin"
EMAIL_INPUT_SELECTOR = 'input[name="email"]'
SEND_MAGIC_LINK_SELECTOR = 'internal:role=button[name="Send magic link"i]'
EMAIL_DELIVERY_WAIT_MS = 10_000


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


@pytest.mark.flaky(reruns=3, reruns_delay=5)
def test_signup_email_extraction(persona: NottePersona):
    with notte.Session(headless=True, tools=[PersonaTool(persona)]) as session:
        goto = session.execute(type="goto", url=CONSOLE_SIGNIN_URL)
        assert goto.success, goto.message

        fill = session.execute(type="fill", selector=EMAIL_INPUT_SELECTOR, value=persona.info.email)
        assert fill.success, fill.message

        wait = session.execute(type="wait", time_ms=1000)
        assert wait.success, wait.message

        send_magic_link = session.execute(type="click", selector=SEND_MAGIC_LINK_SELECTOR)
        assert send_magic_link.success, send_magic_link.message

        wait_for_email = session.execute(type="wait", time_ms=EMAIL_DELIVERY_WAIT_MS)
        assert wait_for_email.success, wait_for_email.message

        inbox = session.execute(action=EmailReadAction(only_unread=False, timedelta=dt.timedelta(minutes=5)))
        assert inbox.success, inbox.message
        assert inbox.data is not None
        assert inbox.data.structured is not None

        emails = inbox.data.structured.get().emails
        matching_emails = [
            email
            for email in emails
            if email.subject == "Sign in to Notte"
            and "console.notte.cc/auth/callback" in email.content
            and "no-reply@mail.notte.cc" == email.sender_email
        ]
        assert matching_emails, f"No recent Notte sign-in email found in {len(emails)} emails"
