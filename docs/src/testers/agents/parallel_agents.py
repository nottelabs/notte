# @sniptest filename=parallel_agents.py
import asyncio

from notte_sdk import NotteClient

client = NotteClient()


async def run_multiple_agents():
    tasks = []

    for task_description in ["Task 1", "Task 2", "Task 3"]:
        with client.Session() as session:
            agent = client.Agent(session=session)
            tasks.append(agent.arun(task=task_description))

    # Run all agents in parallel
    results = await asyncio.gather(*tasks)
    return results


results = asyncio.run(run_multiple_agents())
for i, result in enumerate(results):
    print(f"Agent {i + 1}: {result.answer}")
