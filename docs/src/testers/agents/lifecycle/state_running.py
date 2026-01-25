# @sniptest filename=state_running.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent.start(task="Complete task")
    # Agent state: Running
