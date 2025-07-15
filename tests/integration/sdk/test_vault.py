import os
from unittest import TestCase

import pytest
from dotenv import load_dotenv
from notte_agent.falco.agent import FalcoAgent
from notte_core.actions import FillAction, FormFillAction, WaitAction
from notte_core.credentials.base import BaseVault, CredentialField, EmailField, PasswordField
from notte_core.credentials.types import ValueWithPlaceholder, get_str_value
from notte_core.errors.actions import NoCredentialsFoundError
from notte_sdk import NotteClient
from notte_sdk.errors import NotteAPIError

import notte


def test_vault_in_local_agent():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    vault = client.vaults.create()
    _ = vault.add_credentials(
        url="https://github.com/",
        email="xyz@notte.cc",
        password="xyz",
    )
    with notte.Session() as session:
        agent = notte.Agent(session=session, vault=vault, max_steps=5)
        _ = agent.run(task="Go to the github.com and try to login with the credentials")

    _ = client.vaults.delete(vault.vault_id)


@pytest.mark.asyncio
async def test_vault_replace_form_fill():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    with client.Vault() as vault, notte.Session() as session:
        EMAIL = "xyz@notte.cc"
        PASSWORD = "xyz"
        URL = "https://github.com/"
        _ = vault.add_credentials(
            url="https://github.com/",
            email=EMAIL,
            password=PASSWORD,
        )
        agent = notte.Agent(session=session, vault=vault, max_steps=5).create_agent()
        assert isinstance(agent, FalcoAgent)
        agent.session = session

        # not strictly necessary, but we need a snapshot
        file_path = "tests/data/github_signin.html"
        _ = await session.window.page.goto(url=f"file://{os.path.abspath(file_path)}")
        res = await session.aexecute(WaitAction(time_ms=100))
        assert res.success
        _ = await session.aobserve()
        session.snapshot.metadata.url = URL

        action = FormFillAction(
            value={"email": EmailField.placeholder_value, "current_password": PasswordField.placeholder_value}
        )
        replaced_action = await agent.action_with_credentials(action)
        assert isinstance(replaced_action, FormFillAction)
        assert isinstance(replaced_action.value["email"], ValueWithPlaceholder)
        assert isinstance(replaced_action.value["current_password"], ValueWithPlaceholder)

        assert get_str_value(replaced_action.value["email"]) == EMAIL
        assert get_str_value(replaced_action.value["current_password"]) == PASSWORD


@pytest.mark.asyncio
async def test_vault_replace_fill():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    with client.Vault() as vault, notte.Session() as session:
        EMAIL = "xyz@notte.cc"
        PASSWORD = "xyz"
        URL = "https://github.com/"
        _ = vault.add_credentials(
            url=URL,
            email=EMAIL,
            password=PASSWORD,
        )
        agent = notte.Agent(session=session, vault=vault, max_steps=5).create_agent()
        assert isinstance(agent, FalcoAgent)

        # need session trajectory within agent to get updated
        agent.session = session

        file_path = "tests/data/github_signin.html"
        _ = await session.window.page.goto(url=f"file://{os.path.abspath(file_path)}")

        res = await session.aexecute(WaitAction(time_ms=100))
        assert res.success
        _ = await session.aobserve()
        session.snapshot.metadata.url = URL

        fill_email = FillAction(id="I1", value=EmailField.placeholder_value)
        replaced_email = await agent.action_with_credentials(fill_email)
        assert isinstance(replaced_email, FillAction)
        assert isinstance(replaced_email.value, ValueWithPlaceholder)
        assert get_str_value(replaced_email.value) == EMAIL

        fill_password = FillAction(id="I2", value=PasswordField.placeholder_value)
        replaced_password = await agent.action_with_credentials(fill_password)
        assert isinstance(replaced_password, FillAction)
        assert isinstance(replaced_password.value, ValueWithPlaceholder)
        assert get_str_value(replaced_password.value) == PASSWORD


def test_vault_should_be_deleted_after_exit_context():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    vault_id = None
    with client.Vault() as vault:
        vault_id = vault.vault_id
    assert vault_id is not None
    with pytest.raises(NotteAPIError):
        _ = client.vaults.get(vault_id)


def test_vault_in_remote_agent():
    _ = load_dotenv()

    client = NotteClient()
    # Create a new secure vault
    with client.vaults.create() as vault, client.Session(headless=True) as session:
        # Add your credentials securely
        _ = vault.add_credentials(
            url="https://github.com/",
            email="<your-email>",
            password="<your-password>",
            mfa_secret="AAAAAAAAAAAA",  # pragma: allowlist secret
        )
        # Run an agent with secure credential access
        agent = client.Agent(session=session, vault=vault, max_steps=1)
        _ = agent.run(task="try to login to github.com with the credentials")


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
    with client.vaults.create() as vault:
        with pytest.raises(ValueError):
            _ = vault.add_credentials(
                url="https://github.com/",
                email="xyz@notte.cc",
                password="xyz",  # pragma: allowlist secret
                mfa_secret="999777",  # pragma: allowlist secret
            )


def test_add_correct_otp():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    with client.vaults.create() as vault:
        _ = vault.add_credentials(
            url="https://github.com/",
            email="xyz@notte.cc",
            password="xyz",  # pragma: allowlist secret
            mfa_secret="mysecret",  # pragma: allowlist secret
        )


def test_invalid_credentials_in_local_agent():
    client = NotteClient()

    # storage = notte.FileStorage()
    with client.Vault() as vault, notte.Session() as session:
        agent = notte.Agent(session=session, vault=vault)
        with pytest.raises(NoCredentialsFoundError):
            _ = agent.run(task="go to console.notte.cc and login then retrieve the current active usage.")
