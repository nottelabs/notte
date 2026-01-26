# @sniptest filename=step_details.py
# @sniptest show=6-13
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Navigate and extract")

    for i, step in enumerate(result.steps):
        print(f"Step {i + 1}:")
        print(f"  Action: {step['action']}")
        print(f"  Success: {step['success']}")
        print(f"  Message: {step['message']}")
