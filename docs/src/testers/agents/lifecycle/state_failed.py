# @sniptest filename=state_failed.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    agent.start(task="Find the contact email on example.com")

    result = agent.wait()
    if not result.success:
        # Agent state: Failed
        print(f"Error: {result.answer}")
