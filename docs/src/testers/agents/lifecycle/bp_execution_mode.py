# @sniptest filename=bp_execution_mode.py
import asyncio

from notte_sdk import NotteClient

client = NotteClient()


async def main():
    with client.Session() as session:
        agent = client.Agent(session=session)

        # Simple tasks: Use run()
        result = agent.run(task="Quick task")

        # Multiple agents: Use async
        agent1 = client.Agent(session=session)
        agent2 = client.Agent(session=session)
        results = await asyncio.gather(agent1.arun(task="Task 1"), agent2.arun(task="Task 2"))

        # Long tasks with monitoring: Use start() + polling
        agent.start(task="Long task")
        done = False
        while not done:
            status = agent.status()
            # Update UI, log progress, etc.
            done = True  # placeholder


asyncio.run(main())
