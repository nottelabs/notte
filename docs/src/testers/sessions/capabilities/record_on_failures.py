# @sniptest filename=record_on_failures.py
from notte_sdk import NotteClient

client = NotteClient()

try:
    with client.Session() as session:
        session.execute(type="goto", url="https://example.com")
        # ... automation ...
except Exception:
    replay = session.replay()
    replay.save(f"error_{session.session_id}.mp4")
    raise
