# @sniptest filename=step_limits.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(session=session)
    agent.run(
        task="Find and summarize the top 5 AI news from today",
        max_steps=20,  # Limit to 20 actions
    )
