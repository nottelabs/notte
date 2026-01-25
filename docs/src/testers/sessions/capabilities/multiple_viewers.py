# @sniptest filename=multiple_viewers.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # Open both viewers
    session.viewer_browser()  # Frame-by-frame
    session.viewer_cdp()  # DevTools
