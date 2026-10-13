# @sniptest filename=param_use_vision.py
# @sniptest show=5-8
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(
        session=session,
        use_vision=True,  # Agent can understand images
    )
    status = session.status()
    assert agent.request.use_vision is True
    assert agent.request.session_id == status.session_id
