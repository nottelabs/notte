import asyncio
import os

from notte_agent import Agent
from notte_agent.common.types import AgentResponse
from notte_sdk import NotteClient


async def main():
    # Load environment variables and create vault
    # Required environment variable:
    # - VAULT_ID: the id of your vault
    # - NOTTE_API_KEY: your api key for the sdk
    # - LEETCODE_COM_USERNAME: your leetcode username
    # - LEETCODE_COM_PASSWORD: your leetcode password
    # - NOTTE_API_KEY: your api key for the sdk
    client = NotteClient()

    vault_id = os.getenv("VAULT_ID")
    if vault_id is None:
        raise ValueError("Set VAULT_ID env variable to a valid Notte vault id")

    vault = client.vaults.get(vault_id)

    # only need to do it once in reality
    URL = "leetcode.com"
    if not vault.has_credential(URL):
        vault.add_credentials_from_env(URL)

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
