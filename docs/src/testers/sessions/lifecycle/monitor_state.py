# @sniptest filename=monitor_state.py
import json

from notte_sdk import NotteClient

client = NotteClient()

with client.Session(idle_timeout_minutes=2) as session:
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
# Automatically stopped here.
