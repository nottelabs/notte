from notte_sdk import NotteClient

client = NotteClient()

# Recommended: Use context manager for automatic cleanup
with client.Session(timeout_minutes=10, viewport_width=1920, viewport_height=1080) as session:
    print(f"Session {session.session_id} is active")

    # Access Playwright page
    page = session.page
    page.goto("https://example.com")
    print(f"Page title: {page.title()}")

# Session automatically stopped here
