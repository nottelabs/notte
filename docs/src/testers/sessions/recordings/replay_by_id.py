# @sniptest filename=replay_by_id.py
from notte_sdk import NotteClient

client = NotteClient()

# Get replay for a specific session
replay = client.sessions.replay(session_id="your-session-id")
replay.download("session_replay.mp4")
