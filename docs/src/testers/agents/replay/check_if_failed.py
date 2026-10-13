# @sniptest filename=check_if_failed.py
# @sniptest show=6-12
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    result = agent.run(task="Complete task")

    if not result.success:
        print(f"Agent failed: {result.answer}")
    nb_steps = sum(1 for s in result.steps if s["type"] == "agent_step_start")
    print(f"Completed {nb_steps} steps")
