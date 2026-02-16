# @sniptest filename=goto_new_tab.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://notte.cc/")
    session.execute(type="evaluate_js", code="document.title")
