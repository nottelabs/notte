# @sniptest filename=param_reasoning_model.py
# @sniptest show=5
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session, reasoning_model="anthropic/claude-sonnet-4-5-20250929")
    status = session.status()
    assert agent.request.reasoning_model == "anthropic/claude-sonnet-4-5-20250929"
    assert agent.request.session_id == status.session_id
