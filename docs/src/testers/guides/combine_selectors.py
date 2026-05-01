# @sniptest filename=combine_selectors.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # More specific selector
    session.execute(type="click", selector="div.container >> button:has-text('Submit')")
