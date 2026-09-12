# @sniptest filename=selenium_builtin_page.py
# @sniptest show=1-6
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    page = session.page  # Built-in Playwright page
    assert page.evaluate("1 + 1") == 2
    status = session.status()
