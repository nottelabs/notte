"""Only exact placeholder values are vault placeholders, and unresolved placeholders fail closed.

Login placeholders (email, username, password, MFA) and secret card placeholders (card CVV, card expiration) fail the
action when the vault cannot resolve them, so the literal placeholder is never typed into the page. Card holder and
card number placeholders are also ordinary values that scripts type on purpose (e.g. 'John Doe' or the
'4242 4242 4242 4242' test card): without a matching vault credential they are filled as written.
"""

import asyncio

import pytest
from notte_browser.session import NotteSession
from notte_core.actions import FillAction, FormFillAction, MultiFactorFillAction
from notte_core.credentials import (
    CARD_CVV,
    CARD_EXPIRATION,
    CARD_HOLDER_NAME,
    CARD_NUMBER,
    EMAIL,
    MFA,
    PASSWORD,
    USERNAME,
)
from notte_core.credentials.base import CredentialField, CredentialsDict, CreditCardDict, LocatorAttributes
from notte_core.credentials.types import ValueWithPlaceholder
from notte_core.errors.actions import NoCredentialsFoundError
from notte_core.errors.processing import (
    CredentialFieldValidationError,
    CredentialReplacementError,
    MissingCredentialFieldError,
    VaultLookupError,
)

from tests.mock.mock_vault import MockVault
from tests.mock.snapshot_factory import make_snapshot
from tests.test_vault_credential_redaction import assert_no_secret, capture_logs, error_texts

URL = "https://example.com"
OTHER_URL = "https://other.example.com"
SECRET_EMAIL = "exact-canary-2b8d@example.net"  # pragma: allowlist secret
SECRET_USERNAME = "exact-canary-user-5e1c"  # pragma: allowlist secret
SECRET_PASSWORD = "Exact-Canary-Pw-6a4f1"  # pragma: allowlist secret
MFA_SECRET = "JBSWY3DPEHPK3PXP"  # pragma: allowlist secret
SECRET_CARD: CreditCardDict = {
    "card_holder_name": "Canary Holder 8c2e",
    "card_number": "4000 0566 5566 5556",
    "card_cvv": "917",
    "card_full_expiration": "07/31",
}
SECRETS = (SECRET_EMAIL, SECRET_USERNAME, SECRET_PASSWORD, *SECRET_CARD.values())
EMPTY_ATTRS = LocatorAttributes(type=None, autocomplete=None, outerHTML=None)
PASSWORD_ATTRS = LocatorAttributes(type="password", autocomplete=None, outerHTML='<input type="password">')

NON_SECRET_PLACEHOLDERS = [EMAIL, USERNAME, CARD_HOLDER_NAME, CARD_NUMBER]
SECRET_PLACEHOLDERS = [PASSWORD, MFA, CARD_CVV, CARD_EXPIRATION]
# placeholders filled as written when the vault cannot resolve them
FILLED_AS_IS = [CARD_HOLDER_NAME, CARD_NUMBER]
# values that contain a placeholder without being one
LOOKALIKES = [
    "John Doe Corp",
    "Jane and John Doe",
    "12 John Doe Street, Springfield",
    "contact: user@example.org",
    "user@example.org.uk",
    "cooljohnny15678",
    "4242 4242 4242 42420",
    "mycoolpassword1",
    "9997791",
    "code [CardCVVPlaceholder]",
]


class NoCardVault(MockVault):
    """Vault without a credit card: the lookup fails, as with a remote vault holding no card."""

    def __init__(self, creds_by_url: dict[str, CredentialsDict] | None = None):
        super().__init__(creds_by_url)
        self.card_lookups: int = 0
        self.credential_lookups: int = 0

    async def _get_credentials_impl(self, url: str) -> CredentialsDict | None:
        self.credential_lookups += 1
        return await super()._get_credentials_impl(url)

    async def get_credit_card_async(self) -> CreditCardDict:
        self.card_lookups += 1
        raise RuntimeError(f"no card stored, response body: {{'card_number': '{SECRET_CARD['card_number']}'}}")


class FailingVault(NoCardVault):
    async def _get_credentials_impl(self, url: str) -> CredentialsDict | None:
        raise RuntimeError(f"backend failure, response body: {{'password': '{SECRET_PASSWORD}'}}")


class NoopLocateSession(NotteSession):
    async def locate(self, action):
        return None


def full_vault(url: str = URL) -> MockVault:
    vault = MockVault(
        {
            url: {
                "email": SECRET_EMAIL,
                "username": SECRET_USERNAME,
                "password": SECRET_PASSWORD,
                "mfa_secret": MFA_SECRET,
            }
        }
    )
    vault._card = SECRET_CARD  # pyright: ignore[reportPrivateUsage]
    return vault


def test_secret_placeholders_are_the_expected_fields() -> None:
    secret = {placeholder for placeholder, cls in CredentialField.placeholder_map.items() if cls.secret}
    assert secret == set(SECRET_PLACEHOLDERS)
    assert set(CredentialField.all_placeholders()) - secret == set(NON_SECRET_PLACEHOLDERS)


@pytest.mark.parametrize("value", LOOKALIKES)
def test_values_containing_a_placeholder_are_not_placeholders(value: str) -> None:
    vault = NoCardVault({URL: {"password": SECRET_PASSWORD}})
    for action in (FillAction(id="I1", value=value), FormFillAction(value={"company": value})):
        assert not vault.contains_credentials(action)
        assert not vault.has_unresolved_placeholders(action)
        replaced = asyncio.run(vault.replace_credentials(action, PASSWORD_ATTRS, make_snapshot(URL)))
        assert replaced.model_dump() == action.model_dump()
    # never treated as a placeholder: the vault is not even queried
    assert vault.card_lookups == 0
    assert vault.credential_lookups == 0


@pytest.mark.parametrize("value", NON_SECRET_PLACEHOLDERS + SECRET_PLACEHOLDERS)
def test_placeholders_match_exactly_ignoring_surrounding_whitespace(value: str) -> None:
    vault = MockVault()
    for candidate in (value, f"  {value}\n"):
        assert vault.has_unresolved_placeholders(FillAction(id="I1", value=candidate))
        assert vault.contains_credentials(FormFillAction(value={"full_name": candidate}))


@pytest.mark.parametrize(
    "vault",
    [
        # no credentials for the domain and no card
        NoCardVault({OTHER_URL: {"email": SECRET_EMAIL, "password": SECRET_PASSWORD}}),
        # credentials for the domain, but not the requested fields
        NoCardVault({URL: {"password": SECRET_PASSWORD}}),
        # vault lookups fail
        FailingVault(),
    ],
    ids=["no-credentials", "missing-field", "lookup-error"],
)
@pytest.mark.parametrize("value", FILLED_AS_IS)
def test_unresolved_card_holder_and_number_are_filled_as_is(vault: NoCardVault, value: str) -> None:
    session = NoopLocateSession(vault=vault)
    session.snapshot = make_snapshot(URL)

    with capture_logs() as logs:
        fill = asyncio.run(session._action_with_vault(FillAction(id="I1", value=value)))
        form = asyncio.run(session._action_with_vault(FormFillAction(value={"full_name": value, "first_name": "John"})))
    assert isinstance(fill, FillAction)
    assert fill.value == value
    assert isinstance(form, FormFillAction)
    assert form.value == {"full_name": value, "first_name": "John"}
    assert any("filling the value as-is" in log for log in logs)
    # neither the vault values nor the filled value are logged
    assert_no_secret(logs, SECRETS + (value,))


@pytest.mark.parametrize(
    ("vault", "value", "error_type"),
    [
        # no credentials for the site
        (NoCardVault({OTHER_URL: {"password": SECRET_PASSWORD}}), PASSWORD, NoCredentialsFoundError),
        (NoCardVault({OTHER_URL: {"password": SECRET_PASSWORD}}), MFA, NoCredentialsFoundError),
        (NoCardVault({OTHER_URL: {"email": SECRET_EMAIL}}), EMAIL, NoCredentialsFoundError),
        (NoCardVault({OTHER_URL: {"username": SECRET_USERNAME}}), USERNAME, NoCredentialsFoundError),
        # credentials for the site, but not the requested field
        (NoCardVault({URL: {"email": SECRET_EMAIL}}), PASSWORD, MissingCredentialFieldError),
        (NoCardVault({URL: {"password": SECRET_PASSWORD}}), MFA, MissingCredentialFieldError),
        (NoCardVault({URL: {"password": SECRET_PASSWORD}}), EMAIL, MissingCredentialFieldError),
        (NoCardVault({URL: {"password": SECRET_PASSWORD}}), USERNAME, MissingCredentialFieldError),
        # the lookup fails (remote vaults raise when they hold no credentials for the URL)
        (FailingVault(), PASSWORD, NoCredentialsFoundError),
        (FailingVault(), MFA, NoCredentialsFoundError),
        (FailingVault(), EMAIL, NoCredentialsFoundError),
        (FailingVault(), USERNAME, NoCredentialsFoundError),
        # no card stored
        (NoCardVault(), CARD_CVV, VaultLookupError),
        (NoCardVault(), CARD_EXPIRATION, VaultLookupError),
    ],
)
def test_unresolved_placeholder_fails_closed(vault: NoCardVault, value: str, error_type: type[Exception]) -> None:
    session = NoopLocateSession(vault=vault)
    session.snapshot = make_snapshot(URL)

    for action in (FillAction(id="I1", value=value), FormFillAction(value={"full_name": value, "first_name": "John"})):
        with capture_logs() as logs, pytest.raises(error_type) as exc_info:
            _ = asyncio.run(session._action_with_vault(action))
        assert isinstance(exc_info.value, (CredentialReplacementError, NoCredentialsFoundError))
        assert_no_secret(error_texts(exc_info.value) + logs, SECRETS + (value,))


@pytest.mark.parametrize("value", [CARD_HOLDER_NAME, CARD_NUMBER])
def test_resolved_non_secret_placeholder_on_invalid_target_fails(value: str) -> None:
    """With a saved card, a card placeholder on an input that is not a card field fails so the agent can retarget."""
    vault = full_vault()
    attrs = LocatorAttributes(type="text", autocomplete=None, outerHTML='<input id="search" type="text">')

    with capture_logs() as logs, pytest.raises(CredentialFieldValidationError) as exc_info:
        _ = asyncio.run(vault.replace_credentials(FillAction(id="I1", value=value), attrs, make_snapshot(URL)))
    assert_no_secret(error_texts(exc_info.value) + logs, SECRETS)


def test_secret_fails_even_when_form_also_holds_unresolved_card_holder() -> None:
    vault = NoCardVault({OTHER_URL: {"email": SECRET_EMAIL, "password": SECRET_PASSWORD}})
    session = NoopLocateSession(vault=vault)
    session.snapshot = make_snapshot(URL)

    with pytest.raises(NoCredentialsFoundError):
        _ = asyncio.run(
            session._action_with_vault(FormFillAction(value={"cc_name": CARD_HOLDER_NAME, "password": PASSWORD}))
        )


def test_no_credentials_error_names_the_site_only() -> None:
    vault = NoCardVault({OTHER_URL: {"email": SECRET_EMAIL, "password": SECRET_PASSWORD}})
    session = NoopLocateSession(vault=vault)
    session.snapshot = make_snapshot("https://login.example.com/sso?token=canary-token-71d3")

    with pytest.raises(NoCredentialsFoundError) as exc_info:
        _ = asyncio.run(session._action_with_vault(FillAction(id="I1", value=EMAIL)))
    error = exc_info.value
    assert error.dev_message.startswith("No vault credentials for login.example.com, ")
    assert error.agent_message == error.dev_message
    for text in error_texts(error):
        assert "canary-token-71d3" not in text
        assert EMAIL not in text


def test_placeholders_are_replaced_when_the_vault_has_credentials() -> None:
    vault = full_vault()
    session = NoopLocateSession(vault=vault)
    session.snapshot = make_snapshot(URL)
    form = FormFillAction(
        value={
            "email": EMAIL,
            "username": f" {USERNAME} ",
            "current_password": PASSWORD,
            "cc_name": CARD_HOLDER_NAME,
            "cc_number": CARD_NUMBER,
            "cc_cvv": CARD_CVV,
            "cc_exp": CARD_EXPIRATION,
            "company": "John Doe Corp",
        }
    )

    with capture_logs() as logs:
        updated = asyncio.run(session._action_with_vault(form))
        mfa = asyncio.run(session._action_with_vault(FillAction(id="I1", value=MFA)))
    assert isinstance(updated, FormFillAction)
    expected = {
        "email": SECRET_EMAIL,
        "username": SECRET_USERNAME,
        "current_password": SECRET_PASSWORD,
        "cc_name": SECRET_CARD["card_holder_name"],
        "cc_number": SECRET_CARD["card_number"],
        "cc_cvv": SECRET_CARD["card_cvv"],
        "cc_exp": SECRET_CARD["card_full_expiration"],
    }
    for key, secret in expected.items():
        value = updated.value[key]
        assert isinstance(value, ValueWithPlaceholder)
        assert value.get_secret_value() == secret
    assert updated.value["company"] == "John Doe Corp"
    assert isinstance(mfa, MultiFactorFillAction)
    assert isinstance(mfa.value, ValueWithPlaceholder)
    assert mfa.value.get_secret_value().isdigit()
    assert_no_secret(logs + [repr(updated), updated.model_dump_json()], SECRETS)


PAGE_URL = "about:blank"
FORM_PAGE = """
<form>
    <input id="name" type="text" />
    <input id="company" type="text" />
    <input id="address" type="text" />
    <input id="email" type="email" />
    <input id="username" type="text" />
    <input id="pw" type="password" />
    <input id="otp" type="text" autocomplete="one-time-code" />
    <input id="cc-name" type="text" autocomplete="cc-name" />
    <input id="cc-number" type="text" autocomplete="cc-number" />
    <input id="cc-csc" type="text" autocomplete="cc-csc" />
    <input id="cc-exp" type="text" autocomplete="cc-exp" />
</form>
"""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("vault", "error_type"),
    [
        (NoCardVault({OTHER_URL: {"email": SECRET_EMAIL, "password": SECRET_PASSWORD}}), NoCredentialsFoundError),
        (FailingVault(), NoCredentialsFoundError),
    ],
    ids=["no-credentials", "lookup-error"],
)
async def test_session_without_credentials_fills_ordinary_values_and_fails_placeholders(
    vault: NoCardVault, error_type: type[Exception]
) -> None:
    with capture_logs() as logs:
        async with NotteSession(headless=True, vault=vault) as session:
            await session.window.page.set_content(FORM_PAGE)

            fills = {
                "#name": CARD_HOLDER_NAME,
                "#company": "John Doe Corp",
                "#address": "12 John Doe Street, Springfield",
                "#cc-number": CARD_NUMBER,
                "#cc-name": CARD_HOLDER_NAME,
            }
            for selector, value in fills.items():
                result = await session.aexecute(type="fill", selector=selector, value=value, raise_on_failure=True)
                assert result.success
                assert await session.window.page.input_value(selector) == value

            login_fills = {"#email": EMAIL, "#username": USERNAME, "#pw": PASSWORD, "#otp": MFA}
            card_fills = {"#cc-csc": CARD_CVV, "#cc-exp": CARD_EXPIRATION}
            failures: list[str] = []
            for selector, value in (login_fills | card_fills).items():
                result = await session.aexecute(type="fill", selector=selector, value=value, raise_on_failure=False)
                assert result.success is False
                assert isinstance(result.exception, (CredentialReplacementError, NoCredentialsFoundError))
                if selector in login_fills:
                    assert isinstance(result.exception, error_type)
                # the literal placeholder is never typed into the page
                assert await session.window.page.input_value(selector) == ""
                failures += [result.message, *error_texts(result.exception)]
            placeholders = tuple(login_fills.values()) + tuple(card_fills.values())
            assert_no_secret(failures, SECRETS + placeholders)
    assert_no_secret(logs, SECRETS + (PASSWORD,))


@pytest.mark.asyncio
async def test_session_with_credentials_replaces_placeholders() -> None:
    vault = full_vault(PAGE_URL)
    with capture_logs() as logs:
        async with NotteSession(headless=True, vault=vault) as session:
            await session.window.page.set_content(FORM_PAGE)

            fills = {
                "#email": (EMAIL, SECRET_EMAIL),
                "#username": (USERNAME, SECRET_USERNAME),
                "#pw": (PASSWORD, SECRET_PASSWORD),
                "#cc-name": (CARD_HOLDER_NAME, SECRET_CARD["card_holder_name"]),
                "#cc-number": (CARD_NUMBER, SECRET_CARD["card_number"]),
                "#cc-csc": (CARD_CVV, SECRET_CARD["card_cvv"]),
                "#cc-exp": (CARD_EXPIRATION, SECRET_CARD["card_full_expiration"]),
                "#company": ("John Doe Corp", "John Doe Corp"),
            }
            results = []
            for selector, (value, expected) in fills.items():
                result = await session.aexecute(type="fill", selector=selector, value=value, raise_on_failure=True)
                results.append(result)
                assert await session.window.page.input_value(selector) == expected

            otp = await session.aexecute(type="fill", selector="#otp", value=MFA, raise_on_failure=True)
            results.append(otp)
            code = await session.window.page.input_value("#otp")
            assert code.isdigit() and len(code) == 6
            # timestamps are left out: their digits can contain the 3-digit card CVV by chance
            dumps = [r.model_dump_json(exclude={"started_at", "ended_at"}) for r in results]
            assert_no_secret([r.message for r in results] + dumps, SECRETS)
    assert_no_secret(logs, SECRETS)
