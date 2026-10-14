import os
from pathlib import Path
from unittest import TestCase

import pytest
from dotenv import load_dotenv
from notte_core.actions import FillAction, FormFillAction, WaitAction
from notte_core.credentials import PASSWORD as PASSWORD_PLACEHOLDER
from notte_core.credentials import USERNAME as USERNAME_PLACEHOLDER
from notte_core.credentials.base import BaseVault, CredentialField, EmailField, PasswordField
from notte_core.credentials.types import ValueWithPlaceholder, get_str_value
from notte_sdk import NotteClient
from notte_sdk.errors import NotteAPIError

import notte


async def load_github_signin_fixture(session: notte.Session) -> None:
    fixture_path = Path(__file__).resolve().parents[2] / "data" / "github_signin.html"
    html = fixture_path.read_text(encoding="utf-8")

    async def fulfill_github_login(route):  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
        await route.fulfill(status=200, content_type="text/html", body=html)

    await session.window.page.route("https://github.com/login", fulfill_github_login)
    _ = await session.window.page.goto(url="https://github.com/login")
    res = await session.aexecute(WaitAction(time_ms=100))
    assert res.success
    _ = await session.aobserve()


def test_vault_should_be_deleted_after_exit_context():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    vault_id = None
    with client.Vault() as vault:
        vault_id = vault.vault_id
    assert vault_id is not None
    with pytest.raises(NotteAPIError):
        _ = client.vaults.get(vault_id)


def test_add_credentials_from_env():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    peeple_dict = dict(email="xyz@notte.cc", password="xyz")
    os.environ["PEEPLE_COM_EMAIL"] = peeple_dict["email"]
    os.environ["PEEPLE_COM_PASSWORD"] = peeple_dict["password"]

    test_dict = dict(username="my_xyz_username", password="my_xyz_password")
    os.environ["TEST_COM_USERNAME"] = test_dict["username"]
    os.environ["TEST_COM_PASSWORD"] = test_dict["password"]
    with client.Vault() as vault:
        _ = vault.add_credentials_from_env(url="https://test.peeple.com/ok")
        _ = vault.add_credentials_from_env(url="https://test.com")

        # try get credentials
        with pytest.raises(NotteAPIError):
            credentials = vault.get_credentials(url="https://acounts.google.com")

        credentials = vault.get_credentials(url="https://test.peeple.com/test")
        assert credentials is not None
        TestCase().assertDictEqual(credentials, peeple_dict)

        credentials = vault.get_credentials(url="peeple.com")
        assert credentials is not None
        TestCase().assertDictEqual(credentials, peeple_dict)

        credentials = vault.get_credentials(url="https://test.com/")
        assert credentials is not None
        TestCase().assertDictEqual(credentials, test_dict)


def test_all_credentials_in_system_prompt():
    system_prompt = BaseVault.instructions()
    all_placeholders = CredentialField.all_placeholders()
    missing_placeholder = {placeholder for placeholder in all_placeholders if placeholder not in system_prompt}

    assert len(missing_placeholder) == 0


def test_add_wrong_otp():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    with client.Vault() as vault, pytest.raises(NotteAPIError) as error:
        _ = vault.add_credentials(
            url="https://github.com/",
            email="xyz@notte.cc",
            password="xyz",  # pragma: allowlist secret
            mfa_secret="999777",  # pragma: allowlist secret
        )

    assert error.value.status_code == 422


def test_add_correct_otp():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    with client.Vault() as vault:
        _ = vault.add_credentials(
            url="https://github.com/",
            email="xyz@notte.cc",
            password="xyz",  # pragma: allowlist secret
            mfa_secret="mysecret",  # pragma: allowlist secret
        )


# ============================================
# Session vault integration tests
# ============================================


@pytest.mark.asyncio
async def test_session_form_fill_with_vault_without_observe_uses_live_url():
    """Test form_fill credential replacement snapshots the live page before vault lookup."""
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    base_url = "https://apartment-board-demo-nine.vercel.app"
    login_url = f"{base_url}/auth/signin"
    username = "alder"
    password = "test-password"  # pragma: allowlist secret

    with client.Vault() as vault:
        _ = vault.add_credentials(url=base_url, username=username, password=password)

        with notte.Session(vault=vault, headless=True, idle_timeout_minutes=3, max_duration_minutes=15) as session:

            async def fulfill_login(route):  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
                await route.fulfill(
                    status=200,
                    content_type="text/html",
                    body="""
                        <form>
                            <label for="username">Username</label>
                            <input id="username" autocomplete="username" type="text" />
                            <label for="password">Password</label>
                            <input id="password" autocomplete="current-password" type="password" />
                        </form>
                    """,
                )

            await session.window.page.route(login_url, fulfill_login)

            goto_result = await session.aexecute(type="goto", url=login_url)
            assert goto_result.success

            fill_result = await session.aexecute(
                type="form_fill",
                value={"username": USERNAME_PLACEHOLDER, "password": PASSWORD_PLACEHOLDER},
            )
            assert fill_result.success
            assert session.snapshot.metadata.url == login_url

            values_result = await session.aexecute(
                type="evaluate_js",
                code="""(() => {
                    const usernameInput = document.querySelector(
                        'input#username, input[name="username"], input[autocomplete="username"], input[type="text"]'
                    );
                    const passwordInput = document.querySelector(
                        'input#password, input[type="password"], input[autocomplete="current-password"]'
                    );
                    return {
                        username: usernameInput?.value,
                        password: passwordInput?.value,
                    };
                })()""",
            )
            assert values_result.success
            assert values_result.data is not None
            assert f'"username": "{username}"' in values_result.data.markdown
            assert f'"password": "{password}"' in values_result.data.markdown


@pytest.mark.asyncio
async def test_session_set_vault_enables_credential_replacement():
    """Test that session.set_vault() enables credential replacement via _action_with_vault."""
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    EMAIL = "test@notte.cc"
    PASSWORD = "testpass123"  # pragma: allowlist secret
    URL = "https://github.com/"

    with client.Vault() as vault, notte.Session() as session:
        _ = vault.add_credentials(url=URL, email=EMAIL, password=PASSWORD)

        # Set vault on session directly (not via agent)
        session.set_vault(vault)

        # Load the fixture through a real URL so refreshed snapshots keep matching vault credentials.
        await load_github_signin_fixture(session)

        # Test _action_with_vault replaces credentials
        action = FormFillAction(
            value={"email": EmailField.placeholder_value, "current_password": PasswordField.placeholder_value}
        )
        replaced = await session._action_with_vault(action)

        assert isinstance(replaced, FormFillAction)
        assert isinstance(replaced.value["email"], ValueWithPlaceholder)
        assert isinstance(replaced.value["current_password"], ValueWithPlaceholder)
        assert get_str_value(replaced.value["email"]) == EMAIL
        assert get_str_value(replaced.value["current_password"]) == PASSWORD


@pytest.mark.asyncio
async def test_session_vault_in_constructor():
    """Test that passing vault to session constructor enables credential replacement."""
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    EMAIL = "constructor@notte.cc"
    PASSWORD = "constructorpass"  # pragma: allowlist secret
    URL = "https://github.com/"

    with client.Vault() as vault:
        _ = vault.add_credentials(url=URL, email=EMAIL, password=PASSWORD)

        # Pass vault directly to session constructor
        with notte.Session(vault=vault) as session:
            await load_github_signin_fixture(session)

            action = FormFillAction(value={"email": EmailField.placeholder_value})
            replaced = await session._action_with_vault(action)

            assert isinstance(replaced.value["email"], ValueWithPlaceholder)
            assert get_str_value(replaced.value["email"]) == EMAIL


@pytest.mark.asyncio
async def test_session_fill_action_with_vault():
    """Test that FillAction credentials are replaced via session vault."""
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    EMAIL = "fill@notte.cc"
    URL = "https://github.com/"

    with client.Vault() as vault, notte.Session(vault=vault) as session:
        _ = vault.add_credentials(url=URL, email=EMAIL, password="pw")

        await load_github_signin_fixture(session)

        fill_action = FillAction(id="I1", value=EmailField.placeholder_value)
        replaced = await session._action_with_vault(fill_action)

        assert isinstance(replaced, FillAction)
        assert isinstance(replaced.value, ValueWithPlaceholder)
        assert get_str_value(replaced.value) == EMAIL
