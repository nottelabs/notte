# @sniptest filename=run_agent.py
# @sniptest show=5-6
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session, max_steps=15)
    result = agent.run(task="Find and click the pricing button")
