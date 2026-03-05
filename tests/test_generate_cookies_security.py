"""
Unit tests for the security properties of generate_cookies() and its
FormFillAction credential handling.

These tests do NOT require a live Notte session – they exercise the
credential-masking logic in isolation.
"""

import warnings
from unittest.mock import MagicMock, patch

import pytest
from notte_core.actions import FormFillAction
from notte_core.credentials.base import PasswordField
from notte_core.credentials.types import ValueWithPlaceholder
from notte_sdk.utils import generate_cookies

# ---------------------------------------------------------------------------
# ValueWithPlaceholder masking contract
# ---------------------------------------------------------------------------


def test_value_with_placeholder_str_returns_placeholder() -> None:
    """str() on a ValueWithPlaceholder must return the placeholder, not the secret."""
    secret = "super_secret_password"  # pragma: allowlist secret
    vwp = ValueWithPlaceholder(secret, PasswordField.placeholder_value)

    assert str(vwp) == PasswordField.placeholder_value
    assert secret not in str(vwp)


def test_value_with_placeholder_repr_does_not_leak_secret() -> None:
    """repr() on a ValueWithPlaceholder must not expose the raw secret."""
    secret = "super_secret_password"  # pragma: allowlist secret
    vwp = ValueWithPlaceholder(secret, PasswordField.placeholder_value)

    assert secret not in repr(vwp)
    assert PasswordField.placeholder_value in repr(vwp)


def test_value_with_placeholder_get_secret_value_returns_secret() -> None:
    """get_secret_value() must still return the real credential for actual use."""
    secret = "super_secret_password"  # pragma: allowlist secret
    vwp = ValueWithPlaceholder(secret, PasswordField.placeholder_value)

    assert vwp.get_secret_value() == secret


# ---------------------------------------------------------------------------
# FormFillAction.execution_message() masking
# ---------------------------------------------------------------------------


def test_form_fill_execution_message_masks_value_with_placeholder() -> None:
    """execution_message() must show the placeholder, not the raw secret."""
    secret = "hunter2"  # pragma: allowlist secret
    masked = ValueWithPlaceholder(secret, PasswordField.placeholder_value)
    action = FormFillAction(value={"email": "user@example.com", "current_password": masked})  # type: ignore[arg-type]

    msg = action.execution_message()

    assert secret not in msg
    assert PasswordField.placeholder_value in msg


def test_form_fill_execution_message_plain_email_visible() -> None:
    """Non-sensitive fields (email) should still appear in execution_message()."""
    masked = ValueWithPlaceholder("secret", PasswordField.placeholder_value)  # pragma: allowlist secret
    action = FormFillAction(value={"email": "user@example.com", "current_password": masked})  # type: ignore[arg-type]

    msg = action.execution_message()

    assert "user@example.com" in msg


def test_form_fill_execution_message_plain_string_password_visible() -> None:
    """
    When a plain-string password is stored (e.g. legacy callers), execution_message()
    still returns it verbatim via str().  This test documents the expected behaviour
    so that reviewers are aware: the real protection comes from always wrapping
    passwords in ValueWithPlaceholder before building a FormFillAction.
    """
    action = FormFillAction(value={"email": "user@example.com", "current_password": "plain_pass"})  # type: ignore[arg-type]

    msg = action.execution_message()
    # Plain strings are not masked – this test confirms the behaviour so any
    # future accidental regression (removing ValueWithPlaceholder wrapping) is
    # immediately visible.
    assert "plain_pass" in msg


# ---------------------------------------------------------------------------
# generate_cookies() emits a UserWarning
# ---------------------------------------------------------------------------


def _make_mock_session(*, form_fill_success: bool = True) -> MagicMock:
    """Return a minimal mock RemoteSession sufficient for generate_cookies()."""
    session = MagicMock()

    # session.execute() called with (type="goto", ...) returns a truthy result
    goto_result = MagicMock()
    goto_result.success = True

    form_result = MagicMock()
    form_result.success = form_fill_success
    form_result.message = "ok"

    click_result = MagicMock()
    click_result.success = True

    wait_result = MagicMock()
    wait_result.success = True

    session.execute.side_effect = [goto_result, form_result, click_result, wait_result]
    session.observe.return_value = [MagicMock()]  # one action returned
    session.get_cookies.return_value = [{"name": "session", "value": "abc"}]

    return session


def test_generate_cookies_emits_user_warning(tmp_path) -> None:
    """generate_cookies() must warn the caller that credentials bypass the vault."""
    output_file = str(tmp_path / "cookies.json")
    session = _make_mock_session()

    with (
        patch("builtins.input", return_value="user@example.com"),
        patch("getpass.getpass", return_value="secret"),  # pragma: allowlist secret
        pytest.warns(UserWarning, match="outside the Notte vault"),
    ):
        generate_cookies(session, "https://example.com", output_file)


def test_generate_cookies_warning_mentions_vault(tmp_path) -> None:
    """The warning message must guide the user toward the vault alternative."""
    output_file = str(tmp_path / "cookies.json")
    session = _make_mock_session()

    with (
        patch("builtins.input", return_value="user@example.com"),
        patch("getpass.getpass", return_value="secret"),  # pragma: allowlist secret
    ):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            generate_cookies(session, "https://example.com", output_file)

    user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
    assert len(user_warnings) == 1
    message = str(user_warnings[0].message)
    assert "vault" in message.lower()
    assert "production" in message.lower() or "enterprise" in message.lower()


# ---------------------------------------------------------------------------
# generate_cookies() passes a masked password to FormFillAction
# ---------------------------------------------------------------------------


def test_generate_cookies_password_not_in_form_fill_call(tmp_path) -> None:
    """
    The FormFillAction built inside generate_cookies() must carry a
    ValueWithPlaceholder for the password, not a bare string.
    """
    output_file = str(tmp_path / "cookies.json")
    session = _make_mock_session()
    captured_actions: list[FormFillAction] = []

    original_execute = session.execute.side_effect

    def capture_execute(action=None, **kwargs):
        if isinstance(action, FormFillAction):
            captured_actions.append(action)
        # fall through to the original side_effect iterator
        return next(iter([original_execute(action, **kwargs)]))  # type: ignore[misc]

    # Rebuild side-effects so we can intercept the FormFillAction call
    goto_result = MagicMock(success=True)
    form_result = MagicMock(success=True)
    click_result = MagicMock(success=True)
    wait_result = MagicMock(success=True)
    session.execute.side_effect = None
    call_sequence = [goto_result, form_result, click_result, wait_result]
    call_iter = iter(call_sequence)

    def tracking_execute(action=None, **kwargs):
        if isinstance(action, FormFillAction):
            captured_actions.append(action)
        return next(call_iter)

    session.execute.side_effect = tracking_execute

    with (
        patch("builtins.input", return_value="user@example.com"),
        patch("getpass.getpass", return_value="real_password"),  # pragma: allowlist secret
        warnings.catch_warnings(),
    ):
        warnings.simplefilter("ignore", UserWarning)
        generate_cookies(session, "https://example.com", output_file)

    assert len(captured_actions) == 1
    action = captured_actions[0]
    password_val = action.value.get("current_password")

    # Must be a ValueWithPlaceholder, not a bare string
    assert isinstance(password_val, ValueWithPlaceholder), (
        f"Expected ValueWithPlaceholder for current_password, got {type(password_val)}"
    )
    # The real password must never surface in any string representation
    assert "real_password" not in str(password_val)
    assert "real_password" not in repr(password_val)
    assert "real_password" not in action.execution_message()
