# @sniptest filename=param_reasoning_model.py
# @sniptest show=6
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session, reasoning_model="anthropic/claude-3.5-sonnet")
