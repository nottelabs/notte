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
    response = agent.run(task="Go to the github.com and try to login with the credentials")
    assert not response.success

    _ = client.vaults.delete_vault(vault.vault_id)


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
