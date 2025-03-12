import os

from dotenv import load_dotenv

from notte.agents import Agent
from notte.common.agent.types import AgentResponse
from notte.common.credential_vault.hashicorp.vault import HashiCorpVault

# Load environment variables and create vault
# Required environment variables for HashiCorp Vault:
# - VAULT_URL: The URL of your HashiCorp Vault server
# - VAULT_DEV_ROOT_TOKEN_ID: The root token for authentication in dev mode
_ = load_dotenv()
vault = HashiCorpVault.create_from_env()

# Add leetcode credentials
vault.add_credentials(
    url="https://leetcode.com", username=os.getenv("LEETCODE_USERNAME"), password=os.getenv("LEETCODE_PASSWORD")
)

agent: Agent = Agent(vault=vault)

if __name__ == "__main__":
    response: AgentResponse = agent.run(
        task=(
            "Go to leetcode.com and solve the problem of the day. when you arrive on the page change the programming language to python."
            "First login to leetcode and then resolve the problem of the day"
            "When there is a cloudflare challenge, click on the box to verify that you are human"
        )
    )
    print(response)
