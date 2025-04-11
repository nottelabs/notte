import asyncio
import os

from dotenv import load_dotenv

from notte.agents.falco.agent import FalcoAgent as Agent
from notte.agents.falco.agent import FalcoAgentConfig as AgentConfig
from notte.common.credential_vault.base import CredentialField, EmailField, MFAField, PasswordField, VaultCredentials
from notte.common.credential_vault.hashicorp.vault import HashiCorpVault


async def main():
    _ = load_dotenv()

    # Load environment variables and create vault
    # Required environment variables for HashiCorp Vault:
    # - VAULT_URL: The URL of your HashiCorp Vault server
    # - VAULT_DEV_ROOT_TOKEN_ID: The root token for authentication in dev mode
    vault = HashiCorpVault.create_from_env()

    # Add twitter credentials
    creds: list[CredentialField] = [
        EmailField(value=os.environ["GITHUB_USERNAME"]),
        PasswordField(value=os.environ["GITHUB_PASSWORD"]),
        MFAField(value=os.environ["GITHUB_2FA"]),
    ]
    await vault.add_credentials(VaultCredentials(url="https://github.com", creds=creds))

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
