# @sniptest filename=overview_default.py
# @sniptest show=6-7
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Find the contact email")
    print(result.answer)  # "contact@example.com"
