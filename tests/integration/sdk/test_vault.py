import os

from dotenv import load_dotenv
from notte_agent import Agent
from notte_sdk import NotteClient

_ = load_dotenv()


def test_vault_in_local_agent():
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    vault = client.vaults.create()
    _ = vault.add_credentials(
        url="https://github.com/",
        username="xyz@notte.cc",
        email="xyz@notte.cc",
        password="xyz",
    )
    agent = Agent(vault=vault, max_steps=5, headless=True)
    response = agent.run(task="Go to the github.com and try to login with the credentials")
    assert not response.success


def test_add_credentials_from_env():
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
    os.environ["PEEPLE_COM_EMAIL"] = "xyz@notte.cc"
    os.environ["PEEPLE_COM_PASSWORD"] = "xyz"
    os.environ["TEST_COM_USERNAME"] = "my_xyz_username"
    vault = client.vaults.create()
    _ = vault.add_credentials_from_env(url="https://test.peeple.com/ok")
    _ = vault.add_credentials_from_env(url="https://test.com")

    # try get credentials
    credentials = vault.get_credentials(url="https://acounts.google.com")
    assert credentials is not None
    assert len(credentials.creds) == 0

    credentials = vault.get_credentials(url="https://test.peeple.com")
    assert credentials is not None
    assert len(credentials.creds) == 2

    credentials = vault.get_credentials(url="peeple.com")
    assert credentials is not None
    assert len(credentials.creds) == 2

    credentials = vault.get_credentials(url="https://test.com/")
    assert credentials is not None
    assert len(credentials.creds) == 1
