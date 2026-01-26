# @sniptest filename=handle_optional_popup.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Try to close popup, continue if it's not present
    session.execute(type="press_key", key="Escape", raise_on_failure=False)
