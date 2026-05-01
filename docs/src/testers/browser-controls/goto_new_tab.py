# @sniptest filename=goto_new_tab.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto_new_tab", url="https://example.com/products")
