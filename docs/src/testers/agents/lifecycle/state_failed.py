# @sniptest filename=state_failed.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)

    result = agent.wait()
    if not result.success:
        # Agent state: Failed
        print(f"Error: {result.answer}")
