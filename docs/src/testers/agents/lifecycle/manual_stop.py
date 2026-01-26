# @sniptest filename=manual_stop.py
# @sniptest show=6-12
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    agent.start(task="Long task")

    # Do something...

    # Stop the agent
    agent.stop()
