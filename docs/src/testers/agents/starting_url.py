# @sniptest filename=starting_url.py
# @sniptest show=6-7
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="Find pricing information", url="https://example.com/products")
