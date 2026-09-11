# @sniptest filename=create_session_2.py
# @sniptest show=5-17
from notte_sdk import NotteClient

client = NotteClient()

session = client.Session()
session.start()
try:
    print(f"Session {session.session_id} is active")
    status = session.status()
    if status.status != "active":
        raise RuntimeError("Session is not active")
    page = session.page
    page.goto("https://example.com")
    title = page.title()
finally:
    # Always stop the session
    session.stop()
