# @sniptest filename=selenium_playwright_alternative.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Access the Playwright page directly
    page = session.page

    # Use Playwright for automation
    page.goto("https://example.com")
    print(f"Title: {page.title()}")
