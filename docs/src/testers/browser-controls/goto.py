# @sniptest filename=goto.py
# @sniptest show=1-6
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

status = session.status()
