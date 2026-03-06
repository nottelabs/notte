# @sniptest filename=live_log_streaming.py
# @sniptest show=6-15
from notte_sdk import NotteClient

client = NotteClient()


def monitor_agent():
    with client.Session() as session:
        agent = client.Agent(session=session)
        agent.start(task="Complete task")

        # Stream logs as they happen
        agent.watch_logs(log=True)

        # Get final status
        status = agent.status()
        return status


monitor_agent()
