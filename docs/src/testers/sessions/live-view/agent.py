# @sniptest filename=agent.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(open_viewer=True) as session:
    agent = client.Agent(session=session, max_steps=10)

    result = agent.run(task="Find the pricing page and extract all plan prices")

    print(f"Agent completed: {result.answer}")
