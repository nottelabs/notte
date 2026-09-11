# @sniptest filename=create_session_2.py
import json

from notte_sdk import NotteClient

client = NotteClient()

# Manual lifecycle: always stop in finally.
session = client.Session(idle_timeout_minutes=10)
session.start()
try:
    status = session.status()
    if status.status != "active":
        raise RuntimeError("Session is not active")
    page = session.page
    page.goto("https://example.com")
    print(
        json.dumps(
            {
                "session_id": session.session_id,
                "status": status.status,
                "idle_timeout_minutes": status.idle_timeout_minutes,
                "title": page.title(),
            }
        )
    )
finally:
    session.stop()
