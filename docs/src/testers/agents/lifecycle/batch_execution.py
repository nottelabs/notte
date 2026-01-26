# @sniptest filename=batch_execution.py
import asyncio

from notte_sdk import NotteClient
from notte_sdk.endpoints.agents import BatchRemoteAgent

client = NotteClient()


async def main():
    with client.Session() as session:
        batch_agent = BatchRemoteAgent(session=session, max_steps=10, _client=client)

        # Run 3 agents in parallel, return first success
        result = await batch_agent.run(task="Complete task", n_jobs=3, strategy="first_success")


asyncio.run(main())
