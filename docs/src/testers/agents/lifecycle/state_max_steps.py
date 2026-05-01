# @sniptest filename=state_max_steps.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session, max_steps=5)
    result = agent.run(task="Very complex task")

    if len(result.steps) >= 5:
        # Agent hit max_steps limit
        print("Agent stopped: maximum steps reached")
