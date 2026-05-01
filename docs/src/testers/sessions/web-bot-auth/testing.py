# @sniptest filename=testing.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(
    web_bot_auth=True,
    open_viewer=True,
) as session:
    page = session.page
    page.goto("https://webbotauth.io/test")
    page.screenshot(path="web_bot_auth_test.png")
    print("Check the screenshot to verify authentication status")
