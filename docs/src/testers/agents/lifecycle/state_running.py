# @sniptest filename=state_running.py
# @sniptest show=6-8
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    agent.start(task="Complete task")
    # Agent state: Running
