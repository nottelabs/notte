import asyncio
import os

from dotenv import load_dotenv

from notte.agents import Agent
from notte.common.agent.types import AgentResponse
from notte.common.credential_vault.base import CredentialField, EmailField, PasswordField, VaultCredentials
from notte.common.credential_vault.hashicorp.vault import HashiCorpVault


async def main():
    # Load environment variables and create vault
    # Required environment variables for HashiCorp Vault:
    # - VAULT_URL: The URL of your HashiCorp Vault server
    # - VAULT_DEV_ROOT_TOKEN_ID: The root token for authentication in dev mode
    _ = load_dotenv()


    agent: Agent = Agent()

    response: AgentResponse = await agent.async_run(
        task=(
            "Search for the latest news title about the NBA team the Los Angeles Lakers."
        ),
        url="https://www.google.com"
    )
    print(response)


if __name__ == "__main__":
    asyncio.run(main())
