# @sniptest filename=step_by_step_analysis.py
# @sniptest show=6-14
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Complex task")

    for i, step in enumerate(result.steps):
        print(f"\n=== Step {i + 1} ===")
        print(f"Action: {step.get('action')}")
        print(f"Success: {step.get('success')}")
        print(f"Page URL: {step.get('url')}")
        print(f"Message: {step.get('message')}")
