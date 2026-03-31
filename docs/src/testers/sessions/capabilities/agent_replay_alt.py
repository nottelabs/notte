# @sniptest filename=agent_replay_alt.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    pass  # session actions here

# Get replay after session ends
replay = session.replay()
replay.download("agent_run.mp4")
