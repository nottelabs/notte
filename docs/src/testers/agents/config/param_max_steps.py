# @sniptest filename=param_max_steps.py
# @sniptest show=6-9
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(
        session=session,
        max_steps=20,  # Allow up to 20 actions
    )
