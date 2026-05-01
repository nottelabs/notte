# @sniptest filename=error_handling.py
# @sniptest show=6-12
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Complete task")

    if result.success:
        print(result.answer)
    else:
        print(f"Agent failed: {result.answer}")
