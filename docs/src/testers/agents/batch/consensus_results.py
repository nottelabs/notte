# @sniptest filename=consensus_results.py
import asyncio

from notte_sdk.endpoints.agents import BatchRemoteAgent


async def main():
    batch_agent = BatchRemoteAgent(session=session, max_steps=10, _client=client)

    # Get results from all agents
    results = await batch_agent.run(task="Extract the company's revenue", n_jobs=5, strategy="all_finished")

    # Find consensus
    revenues = [r.answer for r in results if r.success]
    consensus = max(set(revenues), key=revenues.count)


asyncio.run(main())
