import datetime as dt
import uuid

import pytest
from notte_browser.tools.base import EmailReadAction, PersonaTool
from notte_sdk import NotteClient
from notte_sdk.endpoints.personas import NottePersona

import notte
from tests.ci_smtp import require_smtp_configuration, send_test_email

client = NotteClient()

EMAIL_READ_WINDOW = dt.timedelta(minutes=10)
EMAIL_READ_ATTEMPTS = 4
EMAIL_READ_WAIT_MS = 10_000


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
def test_signup_email_extraction():
    require_smtp_configuration()

    with client.Persona(create_vault=False, create_phone_number=False) as persona:
        started_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=10)
        subject = f"Notte signup persona email delivery {uuid.uuid4()}"
        sender = send_test_email(persona.info.email, subject)
        print(f"Sent SMTP email from {sender} to persona {persona.persona_id}: {persona.info.email}")

        with notte.Session(headless=True, tools=[PersonaTool(persona)]) as session:
            emails = []
            for attempt in range(1, EMAIL_READ_ATTEMPTS + 1):
                if attempt > 1:
                    wait_for_email = session.execute(type="wait", time_ms=EMAIL_READ_WAIT_MS)
                    assert wait_for_email.success, wait_for_email.message

                inbox = session.execute(action=EmailReadAction(only_unread=False, timedelta=EMAIL_READ_WINDOW))
                assert inbox.success, inbox.message
                assert inbox.data is not None
                assert inbox.data.structured is not None

                emails = inbox.data.structured.get().emails
                for email in emails:
                    print(
                        "email:",
                        f"subject={email.subject!r}",
                        f"sender={email.sender_email!r}",
                        f"created_at={email.created_at.isoformat()}",
                    )

                matching_emails = [
                    email for email in emails if email.created_at >= started_at and email.subject == subject
                ]
                if matching_emails:
                    return

            subjects = [email.subject for email in emails]
            raise AssertionError(f"No fresh SMTP test email found in {len(emails)} emails. Subjects: {subjects!r}")
