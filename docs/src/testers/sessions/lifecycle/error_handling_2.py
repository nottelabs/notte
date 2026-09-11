# @sniptest filename=error_handling_2.py
# @sniptest show=7-21
from notte_sdk import NotteClient

client = NotteClient()
session_id = None
error_message = None

session = client.Session(idle_timeout_minutes=2)
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
    error_message = str(error)
    print(f"Automation failed: {error_message}")
# Cleanup happens even when automation raises.
