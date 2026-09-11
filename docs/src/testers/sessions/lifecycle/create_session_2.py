from notte_sdk import NotteClient

client = NotteClient()

# Manual management (not recommended)
session = client.Session(timeout_minutes=10)
session.start()

try:
    print(f"Session {session.session_id} is active")
    page = session.page
    page.goto("https://example.com")
finally:
    # Always stop the session
    session.stop()
