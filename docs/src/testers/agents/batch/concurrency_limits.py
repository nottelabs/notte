# @sniptest filename=concurrency_limits.py
import asyncio

from notte_sdk.endpoints.agents import BatchRemoteAgent


async def main():
    batch_agent = BatchRemoteAgent(session=session, _client=client)

    # May hit account concurrency limit
    result = await batch_agent.run(
        task="Task",
        n_jobs=20,  # Might exceed concurrent session limit
    )

    # Safer approach
    result = await batch_agent.run(
        task="Task",
        n_jobs=5,  # Within typical limits
    )


asyncio.run(main())
