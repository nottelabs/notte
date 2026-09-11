# @sniptest filename=error_handling_2.py
import json

from notte_sdk import NotteClient

client = NotteClient()
session = client.Session(idle_timeout_minutes=2)
session_id = None

try:
    session.start()
    try:
        session_id = session.session_id
        session.page.goto("https://example.com")
        raise ValueError("Example automation failure")
    finally:
        session.stop()
except ValueError as error:
    if str(error) != "Example automation failure":
        raise
    print(json.dumps({"session_id": session_id, "error": str(error)}))
# Cleanup happens even when automation raises.
