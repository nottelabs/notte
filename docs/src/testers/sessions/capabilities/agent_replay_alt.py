# @sniptest filename=replay_after_session.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    pass  # session actions here

# Get replay after session ends
replay = session.replay()
replay.download("session_run.mp4")
