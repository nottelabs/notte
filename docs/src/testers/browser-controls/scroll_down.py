# @sniptest filename=scroll_down.py
# @sniptest show=1-7
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://en.wikipedia.org/wiki/Web_browser")
    session.execute(type="scroll_down")

status = session.status()
