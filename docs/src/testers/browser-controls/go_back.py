# @sniptest filename=go_back.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")
    session.execute(type="goto", url="https://example.com/products")

    # Go back to homepage
    session.execute(type="go_back")
