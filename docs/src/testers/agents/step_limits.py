# @sniptest filename=step_limits.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(
        session=session,
        max_steps=20,  # Limit to 20 actions
    )
