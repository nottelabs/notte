import os
from unittest import TestCase

import pytest
from dotenv import load_dotenv
from notte_agent import Agent
from notte_core.credentials.base import BaseVault, CredentialField
from notte_sdk import NotteClient
from notte_sdk.errors import NotteAPIError


def test_vault_in_local_agent():
    _ = load_dotenv()
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    vault = client.vaults.create()
    _ = vault.add_credentials(
        url="https://github.com/",
        email="xyz@notte.cc",
        password="xyz",
    )
    agent = Agent(vault=vault, max_steps=5, headless=True)
    _ = agent.run(task="Go to the github.com and try to login with the credentials")

    _ = client.vaults.delete_vault(vault.vault_id)


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
    with client.vaults.create() as vault:
        # Add your credentials securely
        _ = vault.add_credentials(
            url="https://github.com/",
            email="<your-email>",
            password="<your-password>",
            mfa_secret="AAAAAAAAAAAA",  # pragma: allowlist secret
        )
        # Run an agent with secure credential access
        agent = client.Agent(vault=vault, max_steps=1)
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
    vault = client.vaults.create()
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
