# @sniptest filename=playwright_access.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Access the playwright page
    page = session.page
    page.goto("https://www.google.com")
    screenshot = page.screenshot(path="screenshot.png")
