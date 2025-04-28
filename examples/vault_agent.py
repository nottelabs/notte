import asyncio
import os

from dotenv import load_dotenv
from notte_agent.falco.agent import FalcoAgent as Agent
from notte_agent.falco.agent import FalcoAgentConfig as AgentConfig
from notte_sdk import NotteClient


async def main():
    _ = load_dotenv()

    # Load environment variables and create vault
    # Required environment variable:
    # - VAULT_ID: the id of your vault
    # - NOTTE_API_KEY: your api key for the sdk
    # - GITHUB_COM_EMAIL: your github username
    # - GITHUB_COM_PASSWORD: your github password
    client = NotteClient()

    vault_id = os.getenv("VAULT_ID")
    if vault_id is None:
        raise ValueError("Set VAULT_ID env variable to a valid Notte vault id")

    vault = client.vaults.get(vault_id)

    URL = "github.com"
    if not vault.has_credential(URL):
        vault.add_credentials_from_env(URL)

    config = (
        AgentConfig()
        .cerebras()
        .map_session(lambda session: session.disable_web_security().not_headless().gemini().agent_mode().steps(15))
    )
    agent = Agent(config=config, vault=vault)

    output = await agent.run(
        ("Go to github.com, and login with your provided credentials"),
    )
    print(output)


if __name__ == "__main__":
    # Run the async function
    asyncio.run(main())
