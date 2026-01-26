# @sniptest filename=async_agent.py
import asyncio

from notte_sdk import NotteClient

client = NotteClient()


async def run_agent_task():
    with client.Session() as session:
        agent = client.Agent(session=session)
        result = await agent.arun(task="Extract data from the page")
        return result


# Run async
result = asyncio.run(run_agent_task())
print(result.answer)
