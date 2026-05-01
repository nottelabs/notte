# @sniptest filename=viewer_cdp.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # Opens CDP debugger
    session.viewer_cdp()
