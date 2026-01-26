# @sniptest filename=timeout.py
import asyncio

from notte_sdk.endpoints.agents import BatchRemoteAgent


async def run_with_timeout():
    batch_agent = BatchRemoteAgent(session=session, _client=client)

    try:
        result = await asyncio.wait_for(
            batch_agent.run(task="Task", n_jobs=3),
            timeout=120,  # 2 minute timeout
        )
        return result
    except asyncio.TimeoutError:
        print("Batch execution timed out")
        raise


asyncio.run(run_with_timeout())
