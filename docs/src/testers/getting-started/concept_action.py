# @sniptest filename=concept_action.py
# @sniptest show=4-5
from notte_sdk import NotteClient

client = NotteClient()
session = client.Session()
session.execute(type="goto", url="https://example.com")
session.execute(type="click", selector="button.submit")
