# @sniptest filename=cookie_file.py
# @sniptest show=1-8
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(cookie_file="cookies.json") as session:
    page = session.page
    page.goto("https://example.com")
    # Cookies auto-loaded at start, auto-saved when session ends
    cookies = session.get_cookies()
    assert any(cookie["name"] == "sniptest_cookie" and cookie["value"] == "paired" for cookie in cookies)
    status = session.status()
