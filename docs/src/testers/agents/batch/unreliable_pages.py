# @sniptest filename=unreliable_pages.py
import asyncio

from notte_sdk import NotteClient
from notte_sdk.endpoints.agents import BatchRemoteAgent

client = NotteClient()


async def main():
    # Page sometimes has timing issues
    with client.Session() as session:
        batch_agent = BatchRemoteAgent(session=session, max_steps=10, _client=client)

        # Run 3 attempts
        result = await batch_agent.run(
            task="Click the submit button that appears after 2 seconds", n_jobs=3, strategy="first_success"
        )

        # Much higher success rate than single agent


asyncio.run(main())
