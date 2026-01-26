# @sniptest filename=param_task.py
# @sniptest show=7
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Find the cheapest laptop under $1000 and add it to cart")
