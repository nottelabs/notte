# @sniptest filename=reload.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")
    session.execute(type="reload")
