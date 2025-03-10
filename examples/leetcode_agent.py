import asyncio
import os

from dotenv import load_dotenv

from notte.agents import Agent
from notte.common.agent.types import AgentResponse
from notte.common.credential_vault.hashicorp.vault import HashiCorpVault

# Load environment variables and create vault
_ = load_dotenv()
vault = HashiCorpVault.create_from_env()

# Add leetcode credentials
leetcode_username = os.getenv("LEETCODE_USERNAME")
leetcode_password = os.getenv("LEETCODE_PASSWORD")
if not leetcode_username or not leetcode_password:
    raise ValueError("LEETCODE_USERNAME and LEETCODE_PASSWORD must be set in the .env file.")

vault.add_credentials(url="https://leetcode.com", username=leetcode_username, password=leetcode_password)

agent: Agent = Agent(vault=vault)


async def main() -> AgentResponse:
    return agent.run(
        task=(
            "Go to leetcode.com and solve the problem of the day. when you arrive on the page change the programming language to python."
            "First login to leetcode and then resolve the problem of the day"
            "When there is a cloudflare challenge, click on the box to verify that you are human"
        )
    )


if __name__ == "__main__":
    response: AgentResponse = asyncio.run(main())
    print(response)
