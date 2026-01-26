# @sniptest filename=cookie_file.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(cookie_file="cookies.json") as session:
    page = session.page
    page.goto("https://example.com")
    # Cookies auto-loaded at start, auto-saved when session ends
