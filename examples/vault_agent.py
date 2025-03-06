import asyncio
import os

from dotenv import load_dotenv
from requests.exceptions import ConnectionError

from notte.agents.falco.agent import FalcoAgent as Agent
from notte.agents.falco.agent import FalcoAgentConfig as AgentConfig
from notte.common.credential_vault.hashicorp.vault import HashiCorpVault

# Load environment variables
_ = load_dotenv()

vault_url = os.getenv("VAULT_URL")
vault_token = os.getenv("VAULT_DEV_ROOT_TOKEN_ID")
if not vault_url or not vault_token:
    raise ValueError(""""
VAULT_URL and VAULT_DEV_ROOT_TOKEN_ID must be set in the .env file.
For example if you are running the vault locally:

```
VAULT_URL=http://0.0.0.0:8200
VAULT_DEV_ROOT_TOKEN_ID=<your-vault-dev-root-token-id>
```

""")


# Initialize vault with environment variables
try:
    vault = HashiCorpVault(url=vault_url, token=vault_token)
except ConnectionError:
    vault_not_running_instructions = """
Make sure to start the vault server before running the agent.
Instructions to start the vault server:
> cd src/notte/common/credential_vault/hashicorp
> docker-compose --env-file ../../../../../.env up
"""
    raise ValueError(f"Vault server is not running. {vault_not_running_instructions}")

# Add credentials from environment variables
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
