# @sniptest filename=session_params.py
import asyncio

from notte_sdk import NotteClient
from notte_sdk.endpoints.agents import BatchRemoteAgent

client = NotteClient()


async def main():
    with client.Session(headless=True, proxies="us", browser_type="chrome") as session:
        batch_agent = BatchRemoteAgent(
            session=session, reasoning_model="gemini/gemini-2.0-flash", max_steps=15, use_vision=True, _client=client
        )

        # All parallel agents use same session config
        result = await batch_agent.run(task="Task", n_jobs=3)


asyncio.run(main())
