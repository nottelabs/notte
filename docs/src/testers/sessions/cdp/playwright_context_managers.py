# @sniptest filename=playwright_context_managers.py
from notte_sdk import NotteClient
from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]

client = NotteClient()

with client.Session() as session:
    with sync_playwright() as p:
        # Your code here
        pass
