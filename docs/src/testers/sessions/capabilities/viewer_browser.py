# @sniptest filename=viewer_browser.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # Opens browser viewer
    session.viewer_browser()
