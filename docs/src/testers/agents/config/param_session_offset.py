# @sniptest filename=param_session_offset.py
# @sniptest show=6-12
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    agent = client.Agent(session=session)
    # Execute some actions first
    session.execute(type="goto", url="https://example.com")
    session.execute(type="click", selector="button.search")

    # Agent remembers actions from step 0
    result = agent.run(task="Continue from where we left off", session_offset=0)
