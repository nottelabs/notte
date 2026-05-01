# @sniptest filename=manual.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # Open live viewer
    session.viewer()

    # Continue automation while watching
    session.execute(type="click", selector="button.submit")
