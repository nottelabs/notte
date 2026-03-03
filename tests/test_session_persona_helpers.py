import asyncio
import datetime as dt

import pytest
from notte_browser.session import NotteSession
from notte_browser.tools.base import PersonaTool
from notte_core.actions import FormFillAction
from notte_core.browser.dom_tree import ComputedDomAttributes, DomAttributes, DomNode
from notte_core.browser.node_type import NodeType
from notte_core.browser.observation import Observation
from notte_core.browser.snapshot import BrowserSnapshot, SnapshotMetadata, ViewportData
from notte_core.credentials import EMAIL, PASSWORD
from notte_core.credentials.base import BaseVault
from notte_core.credentials.types import ValueWithPlaceholder
from notte_sdk.endpoints.personas import BasePersona
from notte_sdk.types import EmailResponse, PersonaResponse, SMSResponse

from tests.mock.mock_vault import MockVault


class StubPersona(BasePersona):
    def __init__(
        self,
        emails: list[EmailResponse],
        sms: list[SMSResponse],
        vault: BaseVault | None = None,
        persona_id: str = "persona_test",
    ) -> None:
        self._emails = emails
        self._sms = sms
        self._vault = vault
        self._info = PersonaResponse(
            persona_id=persona_id,
            status="active",
            first_name="Test",
            last_name="Persona",
            email="persona@example.com",
            vault_id="vault_123" if vault else None,
            phone_number=None,
        )

    async def aemails(self, **data):  # type: ignore[override]
        return self._emails

    async def asms(self, **data):  # type: ignore[override]
        return self._sms

    def _get_info(self) -> PersonaResponse:
        return self._info

    def _get_vault(self):  # type: ignore[override]
        return self._vault


def make_snapshot(url: str) -> BrowserSnapshot:
    return BrowserSnapshot(
        metadata=SnapshotMetadata(
            title="mock",
            url=url,
            viewport=ViewportData(
                scroll_x=0,
                scroll_y=0,
                viewport_width=1000,
                viewport_height=1000,
                total_width=1000,
                total_height=1000,
            ),
            tabs=[],
        ),
        html_content="<html></html>",
        a11y_tree=None,
        dom_node=DomNode(
            id="root",
            type=NodeType.OTHER,
            role="WebArea",
            text="",
            children=[],
            attributes=DomAttributes.safe_init(tag_name="div"),
            computed_attributes=ComputedDomAttributes(),
        ),
        screenshot=Observation.empty().screenshot.raw,
    )


def test_session_read_emails_and_sms() -> None:
    emails = [
        EmailResponse(
            subject="Test",
            email_id="email_1",
            created_at=dt.datetime.now(),
            sender_email="sender@example.com",
            sender_name="Sender",
            text_content="Hello",
        )
    ]
    sms = [
        SMSResponse(
            body="123456",
            sms_id="sms_1",
            created_at=dt.datetime.now(),
            sender="+1234567890",
        )
    ]
    persona = StubPersona(emails=emails, sms=sms)
    session = NotteSession(persona=persona)

    email_result = session.read_emails()
    sms_result = session.read_sms()

    assert email_result.success is True
    assert email_result.data is not None
    assert sms_result.success is True
    assert sms_result.data is not None


def test_session_read_emails_requires_persona() -> None:
    session = NotteSession()
    with pytest.raises(ValueError):
        session.read_emails()


def test_session_attach_persona_adds_persona_tool() -> None:
    """Test that attach_persona adds a PersonaTool to session.tools."""
    persona = StubPersona(emails=[], sms=[])
    session = NotteSession()

    # No persona tools initially
    assert not any(isinstance(t, PersonaTool) for t in session.tools)

    session.attach_persona(persona)

    # Now there should be a PersonaTool
    persona_tools = [t for t in session.tools if isinstance(t, PersonaTool)]
    assert len(persona_tools) == 1
    assert persona_tools[0].persona.info.persona_id == "persona_test"


def test_session_attach_persona_does_not_duplicate_tool() -> None:
    """Test that attaching the same persona twice doesn't add duplicate tools."""
    persona = StubPersona(emails=[], sms=[])
    session = NotteSession()

    session.attach_persona(persona)
    session.attach_persona(persona)  # Attach again

    persona_tools = [t for t in session.tools if isinstance(t, PersonaTool)]
    assert len(persona_tools) == 1  # Should still be just one


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


def test_session_read_sms_requires_persona() -> None:
    """Test that read_sms raises ValueError when no persona is attached."""
    session = NotteSession()
    with pytest.raises(ValueError):
        session.read_sms()


def test_session_persona_init_attaches_tool() -> None:
    """Test that passing persona to constructor attaches PersonaTool."""
    persona = StubPersona(emails=[], sms=[])
    session = NotteSession(persona=persona)

    persona_tools = [t for t in session.tools if isinstance(t, PersonaTool)]
    assert len(persona_tools) == 1
    assert session.persona is persona
