import asyncio
import os

from dotenv import load_dotenv

from notte.agents.falco.agent import FalcoAgent as Agent
from notte.agents.falco.agent import FalcoAgentConfig as AgentConfig
from notte.common.credential_vault.hashicorp.vault import HashiCorpVault
from notte_integrations.remote_sessions.steel_pool import SteelBrowserPool

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

leetcode_username = os.getenv("LEETCODE_USERNAME")
leetcode_password = os.getenv("LEETCODE_PASSWORD")

if not leetcode_username or not leetcode_password:
    raise ValueError("LEETCODE_USERNAME and LEETCODE_PASSWORD must be set in the .env file.")

vault.add_credentials(url="https://leetcode.com", username=leetcode_username, password=leetcode_password)

steel_pool = SteelBrowserPool(verbose=True)


async def main():
    await steel_pool.start()

    config = AgentConfig().openai().map_env(lambda env: (env.disable_web_security().not_headless().steps(15)))
    agent = Agent(config=config, vault=vault, pool=steel_pool)

    output = await agent.run(
        (
            "Go to leetcode.com and solve the problem of the day. when you arrive on the page change the programming language to python."
            "First login to leetcode and then resolve the problem of the day"
            "When there is a cloudflare challenge, click on the box to verify that you are human"
        )
    )
    print(output)


# Run the async function
asyncio.run(main())
