# @sniptest filename=bp_cleanup.py
from notte_sdk import NotteClient

client = NotteClient()

# Use context managers for automatic cleanup
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Task")
# Session automatically closed
