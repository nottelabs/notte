# @sniptest filename=configuration.py
from notte_sdk import NotteClient
from notte_sdk.endpoints.sessions import SessionViewerType

# Set default viewer to CDP
client = NotteClient(viewer_type=SessionViewerType.CDP)

with client.Session(open_viewer=True) as session:
    # Opens CDP viewer by default
    session.execute(type="goto", url="https://example.com")
