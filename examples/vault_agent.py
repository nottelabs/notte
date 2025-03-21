import asyncio
import os

from dotenv import load_dotenv

from notte.agents.falco.agent import FalcoAgent as Agent
from notte.agents.falco.agent import FalcoAgentConfig as AgentConfig
from notte.common.credential_vault.hashicorp.vault import HashiCorpVault

# Load environment variables and create vault
# Required environment variables for HashiCorp Vault:
# - VAULT_URL: The URL of your HashiCorp Vault server
# - VAULT_DEV_ROOT_TOKEN_ID: The root token for authentication in dev mode
_ = load_dotenv()
vault = HashiCorpVault.create_from_env()

# Add twitter credentials
vault.add_credentials(
    url="https://x.com", username=os.getenv("TWITTER_USERNAME"), password=os.getenv("TWITTER_PASSWORD")
)

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
