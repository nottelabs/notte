# @sniptest filename=starting_url.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent.run(task="Find pricing information", url="https://example.com/products")
