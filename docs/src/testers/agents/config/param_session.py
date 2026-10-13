# @sniptest filename=param_session.py
# @sniptest show=4-5
from notte_sdk import NotteClient

client = NotteClient()
with client.Session(open_viewer=True) as session:
    agent = client.Agent(session=session)
    status = session.status()
    assert agent.request.session_id == status.session_id
status = client.sessions.status(agent.request.session_id)
