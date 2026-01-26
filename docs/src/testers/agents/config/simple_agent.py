# @sniptest filename=simple_agent.py
# @sniptest show=5-7
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Find contact email")
