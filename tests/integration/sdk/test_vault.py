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
    os.environ["ACCOUNTS_GOOGLE_COM_USERNAME"] = "xyz@notte.cc"
    os.environ["ACCOUNTS_GOOGLE_COM_PASSWORD"] = "xyz"
    os.environ["GITHUB_COM_USERNAME"] = "my_xyz_username"
    vault = client.vaults.create()
    _ = vault.add_credentials_from_env(url="https://accounts.google.com/")
    _ = vault.add_credentials_from_env(url="https://github.com/")

    # try get credentials
    credentials = vault.get_credentials(url="https://accounts.google.com/")
    assert credentials is not None
    assert len(credentials.creds) == 2
