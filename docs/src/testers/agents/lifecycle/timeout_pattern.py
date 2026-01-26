# @sniptest filename=timeout_pattern.py
import asyncio

from notte_sdk import NotteClient


async def run_with_timeout(agent, timeout_seconds=60):
    try:
        result = await asyncio.wait_for(agent.arun(task="Complete task"), timeout=timeout_seconds)
        return result
    except asyncio.TimeoutError:
        agent.stop()
        raise TimeoutError(f"Agent exceeded {timeout_seconds}s timeout")


client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    # Run with 60 second timeout
    result = asyncio.run(run_with_timeout(agent, timeout_seconds=60))
