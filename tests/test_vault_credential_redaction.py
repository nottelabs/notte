"""Credential replacement must never leak vault values and must fail closed.

Every test uses distinctive secret values and asserts that they never show up in exception messages or in
any log line, and that a placeholder that cannot be replaced fails instead of being returned unreplaced.
"""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from loguru import logger
from notte_browser.session import NotteSession
from notte_core import LoggingSetup
from notte_core.actions import FillAction, FormFillAction, GotoAction, MultiFactorFillAction, ScrapeAction
from notte_core.credentials import CARD_CVV, CARD_HOLDER_NAME, EMAIL, MFA, PASSWORD
from notte_core.credentials.base import CredentialsDict, CreditCardDict, LocatorAttributes, PasswordField
from notte_core.credentials.types import ValueWithPlaceholder
from notte_core.errors.actions import NoCredentialsFoundError
from notte_core.errors.base import NotteBaseError
from notte_core.errors.processing import (
    CredentialReplacementError,
    MissingCredentialFieldError,
    VaultLookupError,
)

from tests.mock.mock_vault import MockVault
from tests.mock.snapshot_factory import make_snapshot

URL = "https://example.com"
SECRET_EMAIL = "leak-canary-7f3a@example.net"  # pragma: allowlist secret
SECRET_PASSWORD = "Leak-Canary-Pw-91c2e"  # pragma: allowlist secret
SECRETS = (SECRET_EMAIL, SECRET_PASSWORD)
PASSWORD_ATTRS = LocatorAttributes(type="password", autocomplete=None, outerHTML='<input type="password">')
EMPTY_ATTRS = LocatorAttributes(type=None, autocomplete=None, outerHTML=None)


@contextmanager
def capture_logs() -> Iterator[list[str]]:
    records: list[str] = []
    handler_id = logger.add(lambda message: records.append(str(message)), level="TRACE")
    try:
        # agent configs reset the loguru handlers, which would drop the capture handler
        with patch.object(LoggingSetup, "set_logger_mode", staticmethod(lambda mode: None)):
            yield records
    finally:
        logger.remove(handler_id)


def assert_no_secret(texts: list[str], secrets: tuple[str, ...] = SECRETS) -> None:
    for text in texts:
        for secret in secrets:
            assert secret not in text


def error_texts(error: BaseException) -> list[str]:
    texts = [str(error), repr(error)]
    if isinstance(error, NotteBaseError):
        texts += [error.dev_message, error.user_message, error.agent_message]
    return texts


def make_vault() -> MockVault:
    return MockVault({URL: {"email": SECRET_EMAIL, "password": SECRET_PASSWORD}})


class FailingVault(MockVault):
    """Vault whose backend errors echo stored values, like some HTTP clients do with response bodies."""

    async def _get_credentials_impl(self, url: str) -> CredentialsDict | None:
        raise RuntimeError(f"backend failure, response body: {{'password': '{SECRET_PASSWORD}'}}")

    async def get_credit_card_async(self) -> CreditCardDict:
        raise RuntimeError(f"backend failure, response body: {{'card_number': '{SECRET_PASSWORD}'}}")


class NoopLocateSession(NotteSession):
    async def locate(self, action):
        return None


def test_already_replaced_fill_is_not_replaced_again() -> None:
    vault = make_vault()
    snapshot = make_snapshot(URL)
    action = asyncio.run(vault.replace_credentials(FillAction(id="I1", value=PASSWORD), PASSWORD_ATTRS, snapshot))
    assert isinstance(action.value, ValueWithPlaceholder)
    # the replaced value serializes back to its placeholder ...
    assert vault.contains_credentials(action)
    # ... but it is already resolved
    assert not vault.has_unresolved_placeholders(action)

    with capture_logs() as logs:
        again = asyncio.run(vault.replace_credentials(action, PASSWORD_ATTRS, snapshot))
    assert isinstance(again.value, ValueWithPlaceholder)
    assert again.value.get_secret_value() == SECRET_PASSWORD
    assert_no_secret(logs)


def test_already_replaced_form_fill_is_not_replaced_again() -> None:
    vault = make_vault()
    session = NotteSession(vault=vault)
    session.snapshot = make_snapshot(URL)
    action = FormFillAction(value={"email": EMAIL, "current_password": PASSWORD})
    action = asyncio.run(session._action_with_vault(action))

    with capture_logs() as logs:
        again = asyncio.run(session._action_with_vault(action))
    assert isinstance(again, FormFillAction)
    assert isinstance(again.value["email"], ValueWithPlaceholder)
    assert again.value["email"].get_secret_value() == SECRET_EMAIL
    assert isinstance(again.value["current_password"], ValueWithPlaceholder)
    assert again.value["current_password"].get_secret_value() == SECRET_PASSWORD
    assert_no_secret(logs)


def test_session_skips_action_already_replaced_by_agent() -> None:
    """The agent replaces credentials before handing the action to a session holding the same vault."""
    vault = make_vault()
    session = NoopLocateSession(vault=vault)
    session.snapshot = make_snapshot(URL)
    replaced = asyncio.run(
        vault.replace_credentials(FillAction(id="I1", value=PASSWORD), PASSWORD_ATTRS, session.snapshot)
    )

    with capture_logs() as logs:
        result = asyncio.run(session._action_with_vault(replaced))
    assert result is replaced
    assert_no_secret(logs)


def test_non_fill_actions_are_never_replaced() -> None:
    """Only fill-type actions carry credentials, even if another action's text contains a placeholder."""
    vault = make_vault()
    for action in (
        ScrapeAction(instructions=f"Extract records for {CARD_HOLDER_NAME}"),
        GotoAction(url=f"https://example.com/?user={EMAIL}"),
    ):
        assert not vault.contains_credentials(action)
        assert not vault.has_unresolved_placeholders(action)


def test_form_fill_keeps_regular_values() -> None:
    vault = make_vault()
    session = NotteSession(vault=vault)
    session.snapshot = make_snapshot(URL)
    action = FormFillAction(value={"email": EMAIL, "first_name": "John"})

    updated = asyncio.run(session._action_with_vault(action))
    assert isinstance(updated, FormFillAction)
    assert isinstance(updated.value["email"], ValueWithPlaceholder)
    assert updated.value["first_name"] == "John"


@pytest.mark.parametrize(
    "action",
    [
        FillAction(id="I1", value=PASSWORD + "!"),
        FormFillAction(value={"current_password": "my " + PASSWORD}),  # pragma: allowlist secret
    ],
)
def test_near_miss_placeholder_is_a_regular_value(action: FillAction | FormFillAction) -> None:
    """Only exact placeholders are replaced: a value that merely contains one is filled as written."""
    vault = make_vault()
    session = NoopLocateSession(vault=vault)
    session.snapshot = make_snapshot(URL)
    original = action.model_dump()

    with capture_logs() as logs:
        result = asyncio.run(session._action_with_vault(action))
    assert result is action
    assert result.model_dump() == original
    assert_no_secret(logs, SECRETS + (PASSWORD + "!", "my " + PASSWORD))


def test_missing_credential_field_fails() -> None:
    vault = make_vault()
    session = NoopLocateSession(vault=vault)
    session.snapshot = make_snapshot(URL)

    with capture_logs() as logs, pytest.raises(MissingCredentialFieldError) as exc_info:
        _ = asyncio.run(session._action_with_vault(MultiFactorFillAction(id="I1", value=MFA)))
    assert "mfa_secret" in exc_info.value.dev_message
    assert isinstance(exc_info.value, CredentialReplacementError)
    assert isinstance(exc_info.value, ValueError)
    assert_no_secret(error_texts(exc_info.value) + logs)


def test_no_credentials_for_domain_fails() -> None:
    vault = make_vault()
    session = NotteSession(vault=vault)
    session.snapshot = make_snapshot("https://sso.other-domain.test/login")

    with capture_logs() as logs, pytest.raises(NoCredentialsFoundError):
        _ = asyncio.run(session._action_with_vault(FormFillAction(value={"current_password": PASSWORD})))
    assert_no_secret(logs)


def test_vault_backend_error_is_not_logged_verbatim() -> None:
    vault = FailingVault()
    snapshot = make_snapshot(URL)

    with capture_logs() as logs, pytest.raises(VaultLookupError) as exc_info:
        _ = asyncio.run(vault.replace_credentials(FillAction(id="I1", value=PASSWORD), PASSWORD_ATTRS, snapshot))
    assert any("RuntimeError" in log for log in logs)
    assert exc_info.value.__cause__ is None
    assert_no_secret(error_texts(exc_info.value) + logs)

    with capture_logs() as logs, pytest.raises(VaultLookupError) as card_exc_info:
        _ = asyncio.run(vault.replace_credentials(FillAction(id="I1", value=CARD_CVV), EMPTY_ATTRS, snapshot))
    assert card_exc_info.value.__cause__ is None
    assert_no_secret(error_texts(card_exc_info.value) + logs)


def test_credential_field_repr_hides_value() -> None:
    field = PasswordField(value=SECRET_PASSWORD)
    assert_no_secret([repr(field), str(field)])
    assert field.value == SECRET_PASSWORD


def test_replaced_action_dump_hides_value() -> None:
    vault = make_vault()
    session = NotteSession(vault=vault)
    session.snapshot = make_snapshot(URL)
    action = asyncio.run(session._action_with_vault(FormFillAction(value={"email": EMAIL, "password": PASSWORD})))

    assert_no_secret([repr(action), str(action), action.model_dump_json(), action.execution_message()])


LOGIN_PAGE = """
<form>
    <input id="email" type="email" />
    <input id="pw" type="password" />
    <input id="otp" type="text" autocomplete="one-time-code" />
</form>
"""
PAGE_URL = "about:blank"


@pytest.mark.asyncio
async def test_session_fill_with_vault_does_not_leak_secret() -> None:
    vault = MockVault({PAGE_URL: {"email": SECRET_EMAIL, "password": SECRET_PASSWORD}})
    with capture_logs() as logs:
        async with NotteSession(headless=True, vault=vault) as session:
            await session.window.page.set_content(LOGIN_PAGE)

            email = await session.aexecute(type="fill", selector="#email", value=EMAIL, raise_on_failure=True)
            # an action already replaced upstream (as the agent does) must not be replaced again
            snapshot = await session.window.snapshot()
            replaced = await vault.replace_credentials(
                FillAction(selector="#pw", value=PASSWORD), PASSWORD_ATTRS, snapshot
            )
            password = await session.aexecute(replaced, raise_on_failure=True)

            assert await session.window.page.input_value("#email") == SECRET_EMAIL
            assert await session.window.page.input_value("#pw") == SECRET_PASSWORD
            results = [email, password]
            assert all(r.success for r in results)
            assert_no_secret([r.message for r in results] + [r.model_dump_json() for r in results])
    assert len(logs) > 0
    assert_no_secret(logs)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("creds_url", "selector", "value", "error_type"),
    [
        # no credentials for the current domain (e.g. after an SSO redirect)
        ("https://other.example.com", "#pw", PASSWORD, NoCredentialsFoundError),
        # the field is not stored in the vault
        (PAGE_URL, "#otp", MFA, MissingCredentialFieldError),
    ],
)
async def test_session_fill_fails_closed_when_placeholder_cannot_be_replaced(
    creds_url: str, selector: str, value: str, error_type: type[Exception]
) -> None:
    vault = MockVault({creds_url: {"email": SECRET_EMAIL, "password": SECRET_PASSWORD}})
    with capture_logs() as logs:
        async with NotteSession(headless=True, vault=vault) as session:
            await session.window.page.set_content(LOGIN_PAGE)

            result = await session.aexecute(type="fill", selector=selector, value=value, raise_on_failure=False)
            assert result.success is False
            assert isinstance(result.exception, error_type)
            # the literal placeholder is never typed into the page
            assert await session.window.page.input_value(selector) == ""

            with pytest.raises(error_type) as exc_info:
                _ = await session.aexecute(type="fill", selector=selector, value=value, raise_on_failure=True)
            assert await session.window.page.input_value(selector) == ""
            assert_no_secret([result.message] + error_texts(exc_info.value))
    assert_no_secret(logs)
