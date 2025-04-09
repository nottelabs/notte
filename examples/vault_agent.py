import asyncio
import os

from dotenv import load_dotenv

from notte.agents.falco.agent import FalcoAgent as Agent
from notte.agents.falco.agent import FalcoAgentConfig as AgentConfig
from notte.common.credential_vault.base import CredentialField, EmailField, PasswordField, VaultCredentials
from notte.common.credential_vault.hashicorp.vault import HashiCorpVault

# Load environment variables and create vault
# Required environment variables for HashiCorp Vault:
# - VAULT_URL: The URL of your HashiCorp Vault server
# - VAULT_DEV_ROOT_TOKEN_ID: The root token for authentication in dev mode
_ = load_dotenv()
vault = HashiCorpVault.create_from_env()

# Add twitter credentials
creds: set[CredentialField] = {
    EmailField(value=os.environ["GITHUB_USERNAME"]),
    PasswordField(value=os.environ["GITHUB_PASSWORD"]),
}
vault.add_credentials(VaultCredentials(url="https://github.com", creds=creds))

config = (
    AgentConfig()
    .cerebras()
    .map_env(lambda env: (env.disable_web_security().not_headless().gemini().agent_mode().steps(15)))
)
agent = Agent(config=config, vault=vault)


async def main():
    output = await agent.run(
        ("Go to github.com, and login with your provided credentials"),
    )
    print(output)


# Run the async function
asyncio.run(main())
