# @sniptest filename=concept_session.py
# @sniptest show=4
from notte_sdk import NotteClient

client = NotteClient()
session = client.Session()  # Playwright-compatible browser
