# @sniptest filename=natural_language_task.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Find the cheapest laptop under $1000 and add it to cart")
