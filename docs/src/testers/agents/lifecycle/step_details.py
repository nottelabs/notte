# @sniptest filename=step_details.py
# @sniptest show=6-15
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Navigate and extract")

    # Each entry is a trajectory element: {"type": ..., "value": {...}}
    # Executed actions have type "execution_result"
    actions = [s["value"] for s in result.steps if s["type"] == "execution_result"]
    for i, step in enumerate(actions):
        print(f"Action {i + 1}: {step['action']['type']}")
        print(f"  Success: {step['success']}")
        print(f"  Message: {step['message']}")
