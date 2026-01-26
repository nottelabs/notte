# @sniptest filename=check_if_failed.py
# @sniptest show=6-11
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Complete task")

    if not result.success:
        print(f"Agent failed: {result.answer}")
    print(f"Completed {len(result.steps)} steps")
