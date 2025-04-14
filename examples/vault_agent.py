import asyncio
import os

from dotenv import load_dotenv
from notte_agent.falco.agent import FalcoAgent as Agent
from notte_agent.falco.agent import FalcoAgentConfig as AgentConfig
from notte_integrations.credentials.hashicorp.vault import HashiCorpVault


async def main():
    _ = load_dotenv()

    # Load environment variables and create vault
    # Required environment variables for HashiCorp Vault:
    # - VAULT_URL: The URL of your HashiCorp Vault server
    # - VAULT_DEV_ROOT_TOKEN_ID: The root token for authentication in dev mode
    vault = HashiCorpVault.create_from_env()

    email = os.environ["GITHUB_USERNAME"]
    password = os.environ["GITHUB_PASSWORD"]
    mfa_secret = os.environ["GITHUB_2FA"]

    await vault.add_credentials(
        url="https://github.com", email=email, username=email, password=password, mfa_secret=mfa_secret
    )

    config = (
        AgentConfig()
        .cerebras()
        .map_env(lambda env: (env.disable_web_security().not_headless().gemini().agent_mode().steps(15)))
    )
    agent = Agent(config=config, vault=vault)

    output = await agent.run(
        ("Go to github.com, and login with your provided credentials"),
    )
    print(output)


if __name__ == "__main__":
    # Run the async function
    asyncio.run(main())
