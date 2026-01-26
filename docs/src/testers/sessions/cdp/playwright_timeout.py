# @sniptest filename=playwright_timeout.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(idle_timeout_minutes=20) as session:
    # Long Playwright automation
    pass
