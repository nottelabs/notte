# @sniptest filename=error_handling.py
import json

from notte_sdk import NotteClient

client = NotteClient()
session = client.Session(idle_timeout_minutes=2)
session_id = None

try:
    with session:
        session_id = session.session_id
        session.page.goto("https://example.com")
        raise ValueError("Example automation failure")
except ValueError as error:
    if str(error) != "Example automation failure":
        raise
    print(json.dumps({"session_id": session_id, "error": str(error)}))
# Cleanup happens even when automation raises.
