# @sniptest filename=reload.py
# @sniptest show=1-7
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")
    session.execute(type="reload")

status = session.status()
