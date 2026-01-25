# @sniptest filename=close_popup.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Close any modal or popup
    session.execute(type="press_key", key="Escape")
