# @sniptest filename=selenium_dialogs.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    page = session.page

    # Set up dialog handler before triggering
    page.on("dialog", lambda dialog: dialog.accept())

    page.goto("https://example.com")

    # Click button that shows alert
    page.click("button#show-alert")

    # Dialog is automatically accepted
