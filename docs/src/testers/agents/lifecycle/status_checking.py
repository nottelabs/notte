# @sniptest filename=status_checking.py
# @sniptest show=6-15
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    agent.start(task="Long running task")

    # Check status
    status = agent.status()

    print(f"Agent ID: {status.agent_id}")
    print(f"Current state: {status.status}")
    print(f"Steps completed: {len(status.steps)}")
    print(f"Success: {status.success}")
