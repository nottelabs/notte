# @sniptest filename=switch_tab.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Open multiple tabs
    session.execute(type="goto", url="https://example.com")
    session.execute(type="goto_new_tab", url="https://example.com/products")

    # Switch back to first tab
    session.execute(type="switch_tab", tab_index=0)
