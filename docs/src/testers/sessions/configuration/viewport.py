# @sniptest filename=viewport.py
import json

from notte_sdk import NotteClient

client = NotteClient()

with client.Session(idle_timeout_minutes=2, viewport_width=3840, viewport_height=2160) as session:
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
                "viewport": page.evaluate("({width: window.innerWidth, height: window.innerHeight})"),
            }
        )
    )
# Automatically stopped here.
