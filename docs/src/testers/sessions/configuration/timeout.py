# @sniptest filename=timeout.py
# @sniptest show=5-8
from notte_sdk import NotteClient

client = NotteClient()

# Session closes after 10 minutes of inactivity
with client.Session(idle_timeout_minutes=10) as session:
    page = session.page
    page.goto("https://example.com")

    # Values retained for the external test runner, outside the displayed range.
    status = session.status()
    title = page.title()
