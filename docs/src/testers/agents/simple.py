# @sniptest filename=simple.py
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(task="go to google, and find cat pictures")
