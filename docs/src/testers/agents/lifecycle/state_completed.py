# @sniptest filename=state_completed.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    agent.start(task="Find the contact email on example.com")

    result = agent.wait()
    if result.success:
        # Agent state: Completed
        print(result.answer)
