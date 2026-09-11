# @sniptest filename=proxies_simple.py
# @sniptest show=5-7
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(idle_timeout_minutes=2, proxies=True) as session:
    page = session.page
    page.goto("https://example.com")

    # Values retained for the external test runner, outside the displayed range.
    status = session.status()
    title = page.title()
