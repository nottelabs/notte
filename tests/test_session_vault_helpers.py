import asyncio

import pytest
from notte_browser.session import NotteSession
from notte_core.actions import FillAction, FormFillAction
from notte_core.credentials import EMAIL, PASSWORD, USERNAME
from notte_core.credentials.base import LocatorAttributes
from notte_core.credentials.types import ValueWithPlaceholder
from notte_core.errors.processing import CredentialFieldValidationError

from tests.mock.mock_vault import MockVault
from tests.mock.snapshot_factory import make_snapshot


class FakeWindow:
    def __init__(self, url: str) -> None:
        self.url = url

    async def snapshot(self):
        return make_snapshot(self.url)


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


def test_password_placeholder_on_invalid_element_raises() -> None:
    """A password sentinel typed into a non-password element (e.g. a <label>) must raise instead
    of silently no-op'ing. Otherwise the literal placeholder string is typed into the field."""
    vault = MockVault({"https://example.com": {"username": "real_user", "password": "s3cr3t"}})
    snapshot = make_snapshot("https://example.com")

    # Mimics the locator attrs you get when targeting a <label> instead of <input type="password">:
    # the type attribute is None because <label> has no type.
    label_attrs = LocatorAttributes(type=None, autocomplete=None, outerHTML="<label>Password</label>")
    action = FillAction(id="M2", value=PASSWORD)

    with pytest.raises(CredentialFieldValidationError) as exc_info:
        asyncio.run(vault.replace_credentials(action, label_attrs, snapshot))

    # Error message should name the credential and hint at the wrong-element cause
    assert "password" in exc_info.value.dev_message
    assert PASSWORD in exc_info.value.dev_message

    # And the action value must not have been mutated to a ValueWithPlaceholder — caller decides
    # whether to recover, but the literal placeholder must not silently leak into typing.
    assert action.value == PASSWORD


def test_password_placeholder_on_password_input_substitutes() -> None:
    """Happy path: when the targeted element really is type=password, substitution proceeds."""
    vault = MockVault({"https://example.com": {"username": "real_user", "password": "s3cr3t"}})
    snapshot = make_snapshot("https://example.com")

    input_attrs = LocatorAttributes(
        type="password", autocomplete="current-password", outerHTML='<input type="password">'
    )
    action = FillAction(id="I2", value=PASSWORD)
    updated = asyncio.run(vault.replace_credentials(action, input_attrs, snapshot))

    assert isinstance(updated.value, ValueWithPlaceholder)
    assert updated.value.get_secret_value() == "s3cr3t"


def test_username_placeholder_unaffected_by_validation_change() -> None:
    """UserNameField.validate_element returns True unconditionally, so username substitution
    still works even when targeting a non-input wrapper. This pins the asymmetric design that
    only PasswordField (and other typed fields) gates on element type."""
    vault = MockVault({"https://example.com": {"username": "real_user", "password": "s3cr3t"}})
    snapshot = make_snapshot("https://example.com")

    label_attrs = LocatorAttributes(type=None, autocomplete=None, outerHTML="<label>Username</label>")
    action = FillAction(id="M1", value=USERNAME)
    updated = asyncio.run(vault.replace_credentials(action, label_attrs, snapshot))

    assert isinstance(updated.value, ValueWithPlaceholder)
    assert updated.value.get_secret_value() == "real_user"


def test_session_action_with_vault_propagates_validation_error() -> None:
    """The session-level catch must not swallow CredentialFieldValidationError — otherwise the
    placeholder leaks into the typed value despite the new raise."""
    vault = MockVault({"https://example.com": {"username": "u", "password": "p"}})
    session = NotteSession(vault=vault)
    session.snapshot = make_snapshot("https://example.com")

    # Force the validation-failing path by stubbing locate() to return None: replace_credentials
    # then runs against the default-empty LocatorAttributes (type=None), which fails the
    # PasswordField check.
    async def _no_locator(_action):
        return None

    session.locate = _no_locator  # type: ignore[method-assign]

    action = FillAction(id="M2", value=PASSWORD)
    with pytest.raises(CredentialFieldValidationError):
        asyncio.run(session._action_with_vault(action))
