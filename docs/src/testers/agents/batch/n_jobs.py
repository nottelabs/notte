# @sniptest filename=n_jobs.py
import asyncio

from notte_sdk.endpoints.agents import BatchRemoteAgent


async def main():
    batch_agent = BatchRemoteAgent(session=session, _client=client)

    # Light parallelism (2-3 agents)
    result = await batch_agent.run(task="Task", n_jobs=2)

    # Medium parallelism (3-5 agents)
    result = await batch_agent.run(task="Task", n_jobs=5)

    # Heavy parallelism (5-10 agents)
    result = await batch_agent.run(task="Task", n_jobs=10)


asyncio.run(main())
