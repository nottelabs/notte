# @sniptest filename=stop_session.py
import json

from notte_sdk import NotteClient

client = NotteClient()

# Manual lifecycle: always stop in finally.
session = client.Session(idle_timeout_minutes=2)
session.start()
try:
    status = session.status()
    if status.status != "active":
        raise RuntimeError("Session is not active")
    print(
        json.dumps(
            {
                "session_id": session.session_id,
                "status": status.status,
                "idle_timeout_minutes": status.idle_timeout_minutes,
            }
        )
    )
finally:
    session.stop()
