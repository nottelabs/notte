# @sniptest filename=bp_vision.py
# @sniptest show=5-9
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    # Text-only site
    text_agent = client.Agent(session=session, use_vision=False)

    # Image-heavy site
    agent = client.Agent(session=session, use_vision=True)
    status = session.status()
    assert text_agent.request.use_vision is False
    assert text_agent.request.session_id == status.session_id
    assert agent.request.use_vision is True
    assert agent.request.session_id == status.session_id
