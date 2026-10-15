import datetime as dt
import uuid

import pytest
from notte_browser.errors import InboxActionNotSupportedLocallyError
from notte_core.actions import EmailReadAction
from notte_sdk import NotteClient
from notte_sdk.endpoints.personas import NottePersona

import notte
from tests.ci_smtp import require_smtp_configuration, send_test_email

EMAIL_READ_WINDOW = dt.timedelta(minutes=10)
EMAIL_READ_TIMEOUT_S = 40.0
EMAIL_READ_POLL_INTERVAL_S = 10.0
# A long-lived persona on the staging test account.
PERSONA_ID = "131a21e1-8c8e-4016-80b9-765c0ce4fb5c"


@pytest.fixture
def client() -> NotteClient:
    # Built per test, not at import, so collecting this module never calls the API.
    return NotteClient()


@pytest.fixture
def persona(client: NotteClient) -> NottePersona:
    return client.Persona(PERSONA_ID)


def test_persona_emails(persona: NottePersona):
    emails = persona.emails(only_unread=False)
    assert all(email.email_id for email in emails)


def test_local_session_rejects_inbox_actions(persona: NottePersona):
    with notte.Session(headless=True, persona=persona) as session:
        with pytest.raises(InboxActionNotSupportedLocallyError, match="persona.emails"):
            _ = session.execute(action=EmailReadAction(only_unread=False))


@pytest.mark.flaky(reruns=3, reruns_delay=5)
def test_signup_email_extraction(client: NotteClient):
    require_smtp_configuration()

    with client.Persona(create_vault=False, create_phone_number=False) as persona:
        started_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=10)
        subject = f"Notte signup persona email delivery {uuid.uuid4()}"
        sender = send_test_email(persona.info.email, subject)
        print(f"Sent SMTP email from {sender} to persona {persona.persona_id}: {persona.info.email}")

        # A fresh persona has an empty inbox, so the first email listed is the one just sent.
        emails = persona.wait_for_emails(
            timedelta=EMAIL_READ_WINDOW,
            timeout=EMAIL_READ_TIMEOUT_S,
            poll_interval=EMAIL_READ_POLL_INTERVAL_S,
        )
        for email in emails:
            print(
                "email:",
                f"subject={email.subject!r}",
                f"sender={email.sender_email!r}",
                f"created_at={email.created_at.isoformat()}",
            )

        matching_emails = [email for email in emails if email.created_at >= started_at and email.subject == subject]
        subjects = [email.subject for email in emails]
        assert matching_emails, f"No fresh SMTP test email found in {len(emails)} emails. Subjects: {subjects!r}"
