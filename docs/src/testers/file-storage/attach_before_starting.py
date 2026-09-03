# @sniptest filename=attach_before_starting.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Storage is always available and scoped to the session.
    session.storage.upload("file.pdf")
