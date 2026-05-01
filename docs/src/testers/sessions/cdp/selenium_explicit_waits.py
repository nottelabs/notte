# @sniptest filename=selenium_explicit_waits.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    page = session.page
    page.goto("https://example.com")

    page.wait_for_selector("button")
    page.click("button")
