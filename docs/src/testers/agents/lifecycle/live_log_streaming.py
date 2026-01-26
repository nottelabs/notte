# @sniptest filename=live_log_streaming.py
# @sniptest show=8-19
import asyncio

from notte_sdk import NotteClient

client = NotteClient()


async def monitor_agent():
    with client.Session() as session:
        agent = client.Agent(session=session)
        agent.start(task="Complete task")

        # Stream logs as they happen
        await agent.watch_logs(log=True)

        # Get final status
        status = agent.status()
        return status


asyncio.run(monitor_agent())
