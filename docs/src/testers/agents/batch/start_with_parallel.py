# @sniptest filename=start_with_parallel.py
import asyncio

from notte_sdk.endpoints.agents import BatchRemoteAgent


async def main():
    batch_agent = BatchRemoteAgent(session=session, _client=client)

    # Good starting point
    result = await batch_agent.run(
        task="Task with ~70% success rate",
        n_jobs=3,  # 97% combined success
        strategy="first_success",
    )


asyncio.run(main())
