# @sniptest filename=bp_vision.py
# @sniptest show=7-11
from notte_sdk import NotteClient

client = NotteClient()
with client.Session() as session:
    # Text-only site
    agent = client.Agent(session=session, use_vision=False)

    # Image-heavy site
    agent = client.Agent(session=session, use_vision=True)
