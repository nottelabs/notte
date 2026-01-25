# @sniptest filename=concept_agent.py
# @sniptest show=4-5
from notte_sdk import NotteClient

client = NotteClient()
session = client.Session()
agent = client.Agent(session=session)
agent.run(task="Find the cheapest flight to Paris")
