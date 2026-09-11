# @sniptest filename=quick_start.py
# @sniptest show=5-8
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    print(f"Session ID: {session.session_id}")
    page = session.page  # Playwright-compatible page
    page.goto("https://example.com")

    # Values retained for the external test runner, outside the displayed range.
    status = session.status()
    title = page.title()
