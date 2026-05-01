# @sniptest filename=click.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # Click by CSS selector
    session.execute(type="click", selector="button#submit")

    # Click by ID from observe()
    session.execute(type="click", id="B1")

    # Click by text selector
    session.execute(type="click", selector="button:has-text('Submit')")
