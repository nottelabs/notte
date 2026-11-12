# @sniptest filename=playwright_dialogs.py
# @sniptest show=1-17
from notte_sdk import NotteClient

client = NotteClient()

# "client": your Playwright code answers dialogs, not Notte
with client.Session(dialog_policy="client") as session:
    page = session.page

    # Register the handler before the page opens a dialog
    page.on("dialog", lambda dialog: dialog.accept())

    page.set_content(
        "<button onclick=\"document.title = confirm('Delete this item?') ? 'accepted' : 'dismissed'\">Delete</button>"
    )
    page.click("button")
    title = page.title()
    print(title)  # accepted

    # Retained for the external test runner, outside the displayed range.
    status = session.status()
