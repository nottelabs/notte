import pytest
from dotenv import load_dotenv
from notte_agent import Agent
from notte_sdk import NotteClient

_ = load_dotenv()


@pytest.fixture
def client() -> NotteClient:
    return NotteClient()


def test_vault_in_local_agent(client: NotteClient):
    vault = client.vault.create()
    _ = vault.add_credentials(
        url="https://github.com/",
        username="xyz@notte.cc",
        email="xyz@notte.cc",
        password="xyz",
    )
    agent = Agent(vault=vault, max_steps=5, headless=True)
    response = agent.run(task="Go to the github.com and try to login with the credentials")
    assert not response.success
