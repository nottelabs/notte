import asyncio
import datetime as dt
from typing import TypeVar

import pytest
from notte_browser.errors import InboxActionNotSupportedLocallyError
from notte_browser.session import NotteSession
from notte_core.actions import EmailReadAction, FormFillAction, SmsReadAction
from notte_core.credentials import EMAIL, PASSWORD
from notte_core.credentials.base import BaseVault
from notte_core.credentials.types import ValueWithPlaceholder
from notte_sdk.endpoints.personas import BasePersona
from notte_sdk.types import EmailResponse, PersonaResponse, SMSResponse

from tests.mock.mock_vault import MockVault
from tests.mock.snapshot_factory import make_snapshot

T = TypeVar("T")


class StubPersona(BasePersona):
    def __init__(
        self,
        emails: list[EmailResponse],
        sms: list[SMSResponse],
        vault: BaseVault | None = None,
        persona_id: str = "persona_test",
        empty_reads: int = 0,
    ) -> None:
        self._emails = emails
        self._sms = sms
        # Number of reads that return an empty inbox before the messages "arrive".
        self._empty_reads = empty_reads
        self.nb_reads = 0
        self._vault = vault
        self._info = PersonaResponse(
            persona_id=persona_id,
            status="active",
            first_name="Test",
            last_name="Persona",
            email="persona@example.com",
            internal_email=f"{persona_id}@example.com",
            vault_id="vault_123" if vault else None,
            phone_number=None,
        )

    def _read(self, messages: list[T]) -> list[T]:
        self.nb_reads += 1
        return [] if self.nb_reads <= self._empty_reads else messages

    async def aemails(self, **data):  # type: ignore[override]
        return self._read(self._emails)

    async def asms(self, **data):  # type: ignore[override]
        return self._read(self._sms)

    def _get_info(self) -> PersonaResponse:
        return self._info

    def _get_vault(self):  # type: ignore[override]
        return self._vault


def test_persona_exposes_readable_and_internal_email_addresses() -> None:
    persona = StubPersona(emails=[], sms=[])

    assert persona.email == "persona@example.com"
    assert persona.internal_email == "persona_test@example.com"


def make_email() -> EmailResponse:
    return EmailResponse(
        subject="Test",
        email_id="email_1",
        created_at=dt.datetime.now(),
        sender_email="sender@example.com",
        sender_name="Sender",
        text_content="Hello",
    )


def make_sms() -> SMSResponse:
    return SMSResponse(
        body="123456",
        sms_id="sms_1",
        created_at=dt.datetime.now(),
        sender="+1234567890",
    )


def test_persona_wait_for_emails_and_sms_poll_until_messages_arrive() -> None:
    persona = StubPersona(emails=[make_email()], sms=[make_sms()], empty_reads=2)

    emails = persona.wait_for_emails(timeout=1, poll_interval=0)
    assert [email.email_id for email in emails] == ["email_1"]
    assert persona.nb_reads == 3

    sms = persona.wait_for_sms(timeout=1, poll_interval=0)
    assert [message.sms_id for message in sms] == ["sms_1"]


def test_persona_await_emails_polls_until_messages_arrive() -> None:
    persona = StubPersona(emails=[make_email()], sms=[], empty_reads=1)

    emails = asyncio.run(persona.await_emails(timeout=1, poll_interval=0))
    assert [email.email_id for email in emails] == ["email_1"]


def test_persona_wait_for_emails_times_out() -> None:
    persona = StubPersona(emails=[], sms=[])

    with pytest.raises(TimeoutError):
        _ = persona.wait_for_emails(timeout=0.05, poll_interval=0.01)
    with pytest.raises(TimeoutError):
        _ = asyncio.run(persona.await_sms(timeout=0.05, poll_interval=0.01))


@pytest.mark.parametrize("action", [EmailReadAction(), SmsReadAction()])
def test_local_session_rejects_inbox_actions(action: EmailReadAction | SmsReadAction) -> None:
    session = NotteSession(persona=StubPersona(emails=[make_email()], sms=[make_sms()]))

    with pytest.raises(InboxActionNotSupportedLocallyError, match="persona"):
        _ = asyncio.run(session.aexecute(action))


def test_session_attach_persona_sets_persona() -> None:
    persona = StubPersona(emails=[], sms=[])
    session = NotteSession()
    assert session.persona is None

    session.attach_persona(persona)

    assert session.persona is persona


def test_session_attach_persona_extracts_vault() -> None:
    """Test that attach_persona extracts vault from persona when session has no vault."""
    vault = MockVault({"https://example.com": {"email": "test@test.com", "password": "secret"}})
    persona = StubPersona(emails=[], sms=[], vault=vault)
    session = NotteSession()

    assert session.vault is None  # No vault initially

    session.attach_persona(persona)

    assert session.vault is vault  # Vault extracted from persona


def test_session_attach_persona_preserves_existing_vault() -> None:
    """Test that attach_persona doesn't override an existing vault."""
    existing_vault = MockVault({"https://existing.com": {"email": "existing@test.com", "password": "pw1"}})
    persona_vault = MockVault({"https://persona.com": {"email": "persona@test.com", "password": "pw2"}})
    persona = StubPersona(emails=[], sms=[], vault=persona_vault)

    session = NotteSession(vault=existing_vault)
    session.attach_persona(persona)

    # Should keep the existing vault, not replace with persona's vault
    assert session.vault is existing_vault


def test_session_persona_vault_enables_credential_replacement() -> None:
    """Test that vault extracted from persona enables credential replacement."""
    vault = MockVault({"https://example.com": {"email": "persona@test.com", "password": "persona_pw"}})
    persona = StubPersona(emails=[], sms=[], vault=vault)
    session = NotteSession(persona=persona)  # Attach via constructor
    session.snapshot = make_snapshot("https://example.com")

    action = FormFillAction(value={"email": EMAIL, "current_password": PASSWORD})
    updated = asyncio.run(session._action_with_vault(action))

    assert isinstance(updated.value["email"], ValueWithPlaceholder)
    assert updated.value["email"].get_secret_value() == "persona@test.com"
    assert isinstance(updated.value["current_password"], ValueWithPlaceholder)
    assert updated.value["current_password"].get_secret_value() == "persona_pw"
