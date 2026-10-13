# @sniptest filename=param_max_steps.py
# @sniptest show=5-8
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(
        session=session,
        max_steps=40,  # Allow up to 40 steps (default: 20)
    )
    status = session.status()
    assert agent.request.max_steps == 40
    assert agent.request.session_id == status.session_id
