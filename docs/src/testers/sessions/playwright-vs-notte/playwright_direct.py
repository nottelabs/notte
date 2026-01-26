# @sniptest filename=playwright_direct.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    page = session.page
    page.goto("https://example.com")
    page.fill("input[name='email']", "user@example.com")
    page.click("button[type='submit']")
