# @sniptest filename=viewport.py
# @sniptest show=5-8
from notte_sdk import NotteClient

client = NotteClient()

# 4K resolution
with client.Session(viewport_width=3840, viewport_height=2160) as session:
    page = session.page
    page.goto("https://example.com")

    # Values retained for the external test runner, outside the displayed range.
    status = session.status()
    title = page.title()
    viewport = page.evaluate("({width: window.innerWidth, height: window.innerHeight})")
