# @sniptest filename=agent_replay_alt.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Alternative: get from session
    replay = session.replay()
    replay.save("agent_run.mp4")
