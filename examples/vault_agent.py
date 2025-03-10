import asyncio
import os

from dotenv import load_dotenv

from notte.agents.falco.agent import FalcoAgent as Agent
from notte.agents.falco.agent import FalcoAgentConfig as AgentConfig
from notte.common.credential_vault.hashicorp.vault import HashiCorpVault

# Load environment variables and create vault
_ = load_dotenv()
vault = HashiCorpVault.create_from_env()

# Add twitter credentials
twitter_username = os.getenv("TWITTER_USERNAME")
twitter_password = os.getenv("TWITTER_PASSWORD")
if not twitter_username or not twitter_password:
    raise ValueError("TWITTER_USERNAME and TWITTER_PASSWORD must be set in the .env file.")

vault.add_credentials(url="https://x.com", username=twitter_username, password=twitter_password)

config = AgentConfig().cerebras().map_env(lambda env: (env.disable_web_security().not_headless().cerebras().steps(15)))
agent = Agent(config=config, vault=vault)


async def main():
    output = await agent.run(
        (
            "Go to x.com, and make a post that we are extremelly happy to introduce a new feature on Notte "
            "we are launching a password vault components enabling agents to connect to more websites"
        ),
    )
    print(output)


# Run the async function
asyncio.run(main())
