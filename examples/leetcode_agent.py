import asyncio
import os

from dotenv import load_dotenv
from notte_agent import Agent
from notte_agent.common.types import AgentResponse
from notte_core.common.credentials.base import CredentialField, EmailField, PasswordField, VaultCredentials
from notte_integrations.credentials.hashicorp.vault import HashiCorpVault


async def main():
    # Load environment variables and create vault
    # Required environment variables for HashiCorp Vault:
    # - VAULT_URL: The URL of your HashiCorp Vault server
    # - VAULT_DEV_ROOT_TOKEN_ID: The root token for authentication in dev mode
    _ = load_dotenv()
    vault = HashiCorpVault.create_from_env()

    # Add leetcode credentials
    creds: list[CredentialField] = [
        EmailField(value=os.environ["LEETCODE_USERNAME"]),
        PasswordField(value=os.environ["LEETCODE_PASSWORD"]),
    ]
    await vault.add_credentials(VaultCredentials(url="https://leetcode.com", creds=creds))

    agent: Agent = Agent(vault=vault)

    response: AgentResponse = agent.run(
        task=(
            "Go to leetcode.com and solve the problem of the day. when you arrive on the page change the programming language to python."
            "First login to leetcode and then resolve the problem of the day"
            "When there is a cloudflare challenge, click on the box to verify that you are human"
        )
    )
    print(response)


if __name__ == "__main__":
    asyncio.run(main())
