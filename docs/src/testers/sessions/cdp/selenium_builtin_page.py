# @sniptest filename=selenium_builtin_page.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    page = session.page  # Built-in Playwright page
