# @sniptest filename=scroll_up.py
# @sniptest show=1-8
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://en.wikipedia.org/wiki/Web_browser")
    session.execute(type="scroll_down")
    session.execute(type="scroll_up")

status = session.status()
