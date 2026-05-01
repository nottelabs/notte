# @sniptest filename=selenium_unique_selectors.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    page = session.page
    page.goto("https://example.com")

    # Good
    page.click('button[data-testid="submit"]')

    # Avoid
    page.click("button:nth-child(3)")
