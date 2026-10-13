# @sniptest filename=selenium_playwright_alternative.py
# @sniptest show=1-11
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Access the Playwright page directly
    page = session.page

    # Use Playwright for automation
    page.goto("https://example.com")
    print(f"Title: {page.title()}")
    status = session.status()
