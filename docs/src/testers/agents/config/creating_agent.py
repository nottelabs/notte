# @sniptest filename=creating_agent.py
# @sniptest show=1-13
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    agent = client.Agent(
        session=session,
        reasoning_model="gemini/gemini-2.0-flash",
        use_vision=True,
        max_steps=15,
        # vault=vault,  # Optional
        # persona=persona,  # Optional
    )
    assert agent.request.reasoning_model == "gemini/gemini-2.0-flash"
    assert agent.request.use_vision is True
    assert agent.request.max_steps == 15
    assert agent.request.session_id == session.session_id
status = client.sessions.status(agent.request.session_id)
