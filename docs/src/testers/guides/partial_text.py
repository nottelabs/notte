# @sniptest filename=partial_text.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Partial text match (more robust)
    session.execute(type="click", selector="button:has-text('Submit')")
