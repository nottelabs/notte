# @sniptest filename=create_session.py
# @sniptest show=5-12
from notte_sdk import NotteClient

client = NotteClient()

# Recommended: Use context manager for automatic cleanup
with client.Session(viewport_width=1920, viewport_height=1080) as session:
    print(f"Session {session.session_id} is active")

    # Access Playwright page
    page = session.page
    page.goto("https://example.com")
    print(f"Page title: {page.title()}")

    # Values retained for the external test runner, outside the displayed range.
    status = session.status()
    title = page.title()
    viewport = page.evaluate("({width: window.innerWidth, height: window.innerHeight})")
