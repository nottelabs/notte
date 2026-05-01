# @sniptest filename=simple_agent.py
# @sniptest show=4-6
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Find contact email")
