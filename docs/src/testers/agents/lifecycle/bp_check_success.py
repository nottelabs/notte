# @sniptest filename=bp_check_success.py
# @sniptest show=6-15
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)

    result = agent.run(task="Critical task")

    if not result.success:
        # Don't proceed if agent failed
        raise RuntimeError(f"Critical task failed: {result.answer}")

    # Safe to proceed with result
    print(result.answer)
