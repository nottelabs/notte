# @sniptest filename=quick_start.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(web_bot_auth=True) as session:
    page = session.page
    page.goto("https://example.com")
    # All requests are automatically signed
