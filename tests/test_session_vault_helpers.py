import asyncio

from notte_browser.session import NotteSession
from notte_core.actions import FillAction, FormFillAction, MultiFactorFillAction
from notte_core.credentials import EMAIL, MFA, PASSWORD, USERNAME
from notte_core.credentials.types import ValueWithPlaceholder

from tests.mock.mock_vault import MockVault
from tests.mock.snapshot_factory import make_snapshot


class FakeWindow:
    def __init__(self, url: str) -> None:
        self.url = url

    async def snapshot(self):
        return make_snapshot(self.url)


class NoopLocateSession(NotteSession):
    async def locate(self, action):
        return None


def test_session_vault_replaces_form_fill_placeholders() -> None:
    vault = MockVault({"https://example.com": {"email": "real@example.com", "password": "s3cr3t"}})
    session = NotteSession(vault=vault)
    session.snapshot = make_snapshot("https://example.com")

    action = FormFillAction(value={"email": EMAIL, "current_password": PASSWORD})
    updated = asyncio.run(session._action_with_vault(action))

    assert isinstance(updated.value["email"], ValueWithPlaceholder)
    assert updated.value["email"].get_secret_value() == "real@example.com"
    assert str(updated.value["email"]) == EMAIL
    assert isinstance(updated.value["current_password"], ValueWithPlaceholder)
    assert updated.value["current_password"].get_secret_value() == "s3cr3t"


def test_session_vault_refreshes_snapshot_from_window() -> None:
    vault = MockVault({"https://example.com": {"username": "fresh-user"}})
    session = NotteSession(vault=vault)
    session._window = FakeWindow("https://example.com")  # pyright: ignore[reportAttributeAccessIssue]

    action = FormFillAction(value={"username": USERNAME})
    updated = asyncio.run(session._action_with_vault(action))

    assert session.snapshot.metadata.url == "https://example.com"
    assert isinstance(updated.value["username"], ValueWithPlaceholder)
    assert updated.value["username"].get_secret_value() == "fresh-user"


def test_session_vault_uses_fresh_snapshot_instead_of_stale_snapshot() -> None:
    vault = MockVault(
        {
            "https://old.example.com": {"username": "stale-user"},
            "https://example.com": {"username": "fresh-user"},
        }
    )
    session = NotteSession(vault=vault)
    session.snapshot = make_snapshot("https://old.example.com")
    session._window = FakeWindow("https://example.com")  # pyright: ignore[reportAttributeAccessIssue]

    action = FormFillAction(value={"username": USERNAME})
    updated = asyncio.run(session._action_with_vault(action))

    assert session.snapshot.metadata.url == "https://example.com"
    assert isinstance(updated.value["username"], ValueWithPlaceholder)
    assert updated.value["username"].get_secret_value() == "fresh-user"


def test_session_set_vault_enables_credential_replacement() -> None:
    """Test that set_vault() enables credential replacement for actions."""
    vault = MockVault({"https://example.com": {"email": "test@test.com", "password": "pw123"}})
    session = NotteSession()  # No vault initially
    session.snapshot = make_snapshot("https://example.com")

    # Without vault, action should pass through unchanged
    action = FormFillAction(value={"email": EMAIL})
    unchanged = asyncio.run(session._action_with_vault(action))
    assert unchanged.value["email"] == EMAIL  # Still a placeholder string

    # After setting vault, credentials should be replaced
    session.set_vault(vault)
    updated = asyncio.run(session._action_with_vault(action))
    assert isinstance(updated.value["email"], ValueWithPlaceholder)
    assert updated.value["email"].get_secret_value() == "test@test.com"


def test_session_vault_ignores_non_fill_actions() -> None:
    """Test that non-fill actions pass through without credential replacement."""
    from notte_core.actions import ClickAction, GotoAction

    vault = MockVault({"https://example.com": {"email": "test@test.com", "password": "pw123"}})
    session = NotteSession(vault=vault)
    session.snapshot = make_snapshot("https://example.com")

    # ClickAction should pass through unchanged
    click = ClickAction(id="B1")
    click_result = asyncio.run(session._action_with_vault(click))
    assert click_result is click  # Same object, unchanged

    # GotoAction should pass through unchanged
    goto = GotoAction(url="https://example.com")
    goto_result = asyncio.run(session._action_with_vault(goto))
    assert goto_result is goto  # Same object, unchanged


def test_session_vault_action_without_placeholders_passes_through() -> None:
    """Test that fill actions without credential placeholders pass through unchanged."""
    vault = MockVault({"https://example.com": {"email": "test@test.com", "password": "pw"}})
    session = NotteSession(vault=vault)
    session.snapshot = make_snapshot("https://example.com")

    # Action with regular values (not credential placeholders like EMAIL, PASSWORD)
    action = FormFillAction(value={"first_name": "John", "city": "New York"})
    result = asyncio.run(session._action_with_vault(action))
    # Should pass through unchanged since no placeholders
    assert result is action


def test_session_vault_preserves_selector_when_fill_mfa_becomes_multi_factor_fill() -> None:
    mfa_secret = "AAAAAAAAAAAA"  # pragma: allowlist secret
    vault = MockVault({"https://example.com": {"email": "test@test.com", "password": "pw", "mfa_secret": mfa_secret}})
    session = NoopLocateSession(vault=vault)
    session.snapshot = make_snapshot("https://example.com")

    action = FillAction(selector='internal:role=textbox[name="Enter code"i]', value=MFA)
    updated = asyncio.run(session._action_with_vault(action))

    assert isinstance(updated, MultiFactorFillAction)
    assert updated.id == ""
    assert updated.selector is not None
    assert updated.selector.playwright_selector == 'internal:role=textbox[name="Enter code"i]'
    assert isinstance(updated.value, ValueWithPlaceholder)
    assert len(updated.value.get_secret_value()) == 6
    assert updated.value.get_secret_value().isdigit()
