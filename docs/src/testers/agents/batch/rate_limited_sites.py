# @sniptest filename=rate_limited_sites.py
import asyncio

from notte_sdk import NotteClient
from notte_sdk.endpoints.agents import BatchRemoteAgent

client = NotteClient()


async def main():
    # Some agents might get rate limited
    with client.Session(proxies="residential") as session:
        batch_agent = BatchRemoteAgent(session=session, max_steps=15, _client=client)

        # Run 5 agents from different IPs
        result = await batch_agent.run(task="Extract product data", n_jobs=5, strategy="first_success")


asyncio.run(main())
