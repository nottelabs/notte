# @sniptest filename=async_only.py
import asyncio

from notte_sdk.endpoints.agents import BatchRemoteAgent


async def run_batch():
    batch_agent = BatchRemoteAgent(session=session, _client=client)
    result = await batch_agent.run(task="Task", n_jobs=3)
    return result


# Must use asyncio.run
result = asyncio.run(run_batch())
