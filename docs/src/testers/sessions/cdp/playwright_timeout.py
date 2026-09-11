# @sniptest filename=playwright_timeout.py
# @sniptest show=1-7
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(idle_timeout_minutes=20, max_duration_minutes=20) as session:
    # Long Playwright automation
    pass
    status = session.status()
