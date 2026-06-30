import datetime as dt
import os
import smtplib
import uuid
from email.message import EmailMessage

import pytest
from notte_browser.errors import NoToolProvidedError
from notte_browser.tools.base import EmailReadAction, PersonaTool
from notte_sdk import NotteClient
from notte_sdk.endpoints.personas import NottePersona

import notte

client = NotteClient()

SMTP_SERVER_ENV = "SMTP_SERVER"
SMTP_PORT_ENV = "SMTP_PORT"
SMTP_USERNAME_ENV = "EMAIL_SENDER"
SMTP_PASSWORD_ENV = "EMAIL_PASSWORD"  # pragma: allowlist secret
SMTP_STARTTLS_ENV = "SMTP_STARTTLS"
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


def _send_test_email(recipient: str, subject: str) -> str:
    missing_env = [name for name in [SMTP_SERVER_ENV, SMTP_USERNAME_ENV, SMTP_PASSWORD_ENV] if os.getenv(name) is None]
    if missing_env:
        pytest.skip(f"{', '.join(missing_env)} required")

    server = os.getenv(SMTP_SERVER_ENV)
    username = os.getenv(SMTP_USERNAME_ENV)
    password = os.getenv(SMTP_PASSWORD_ENV)
    assert server is not None
    assert username is not None
    assert password is not None

    host, _, server_port = server.partition(":")
    port = int(os.getenv(SMTP_PORT_ENV, server_port or "587"))
    message = EmailMessage()
    message["From"] = username
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(f"Notte persona email delivery test: {subject}")

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as server:
            server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            if os.getenv(SMTP_STARTTLS_ENV, "true").lower() != "false":
                server.starttls()
            server.login(username, password)
            server.send_message(message)

    return username


@pytest.mark.flaky(reruns=3, reruns_delay=5)
def test_signup_email_extraction():
    missing_env = [name for name in [SMTP_SERVER_ENV, SMTP_USERNAME_ENV, SMTP_PASSWORD_ENV] if os.getenv(name) is None]
    if missing_env:
        pytest.skip(f"{', '.join(missing_env)} required")

    with client.Persona(create_vault=False, create_phone_number=False) as persona:
        started_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=10)
        subject = f"Notte signup persona email delivery {uuid.uuid4()}"
        sender = _send_test_email(persona.info.email, subject)
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
