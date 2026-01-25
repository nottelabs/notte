# @sniptest filename=manual_stop.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent.start(task="Long task")

    # Do something...

    # Stop the agent
    agent.stop()
