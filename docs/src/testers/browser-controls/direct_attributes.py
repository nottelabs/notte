# @sniptest filename=direct_attributes.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # By ID from observe()
    session.execute(type="click", id="B1")

    # By selector
    session.execute(type="click", selector="button[type='submit']")

    # By placeholder selector
    session.execute(type="fill", selector="input[placeholder='Enter email']", value="user@example.com")

    # By ARIA label selector
    session.execute(type="click", selector="button[aria-label='Close dialog']")
