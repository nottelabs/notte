# @sniptest filename=parallel_agents.py
import asyncio

from notte_sdk import NotteClient

client = NotteClient()


async def run_multiple_agents():
    async def run_one(task_description: str):
        with client.Session() as session:
            agent = client.Agent(session=session)
            agent.start(task=task_description)
            return await agent.async_watch_logs_and_wait()

    # Run all agents in parallel (each with its own session)
    results = await asyncio.gather(*[run_one(t) for t in ["Task 1", "Task 2", "Task 3"]])
    return results


results = asyncio.run(run_multiple_agents())
for i, result in enumerate(results):
    print(f"Agent {i + 1}: {result.answer}")
