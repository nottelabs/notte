# @sniptest filename=start_wait.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)

    # Start agent (returns immediately)
    agent.start(task="Complete this task")

    # Do other work here...

    # Wait for completion
    result = agent.wait()
