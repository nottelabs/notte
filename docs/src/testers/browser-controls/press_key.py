# @sniptest filename=press_key.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # Press Enter
    session.execute(type="press_key", key="Enter")

    # Press Escape
    session.execute(type="press_key", key="Escape")

    # Press Tab
    session.execute(type="press_key", key="Tab")
