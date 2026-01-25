# @sniptest filename=name_recordings.py
from datetime import datetime

from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")
    replay = session.replay()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    replay.save(f"login_test_{session.session_id}_{timestamp}.mp4")
